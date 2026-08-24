import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AuditLog
from apps.inventory.models import Brand, Category, Product
from apps.quotations.models import Quotation, QuotationItem


@override_settings(SECURE_SSL_REDIRECT=False)
class QuotationViewTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='creator', password='password')
        self.editor = User.objects.create_user(username='editor', password='password')
        self.editor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='quotations',
            codename__in=['add_quotation', 'view_quotation', 'change_quotation', 'delete_quotation'],
        ))
        self.client.force_login(self.editor)

        category = Category.objects.create(name='Wall Clocks')
        brand = Brand.objects.create(name='Acme')
        self.product = Product.objects.create(
            sku='CLOCK-1',
            category=category,
            brand=brand,
            default_selling_price=Decimal('100.00'),
            average_cost=Decimal('60.00'),
            total_stock=7,
        )
        self.quotation = Quotation.objects.create(
            title='Original quotation',
            quotation_date=date(2026, 8, 20),
            valid_until=date(2026, 9, 20),
            status=Quotation.Status.SENT,
            client_name='Original Client',
            subtotal=Decimal('200.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('190.00'),
            created_by=self.creator,
        )
        self.original_item = QuotationItem.objects.create(
            quotation=self.quotation,
            product=self.product,
            quantity=2,
            unit_price=Decimal('100.00'),
        )

    def update_url(self):
        return reverse('quotations:api_quotation_update', args=[self.quotation.pk])

    def edit_url(self):
        return reverse('quotations:quotation_edit', args=[self.quotation.pk])

    def payload(self, **overrides):
        payload = {
            'title': 'Updated quotation',
            'quotation_date': '2026-08-24',
            'valid_until': '2026-09-24',
            'client_name': 'Updated Client',
            'client_phone': '01700000000',
            'client_address': 'Updated address',
            'discount': '25.00',
            'notes': 'Updated notes',
            'items': [
                {
                    'product_id': self.product.pk,
                    'is_custom': False,
                    'custom_description': '',
                    'quantity': 3,
                    'unit_price': '120.00',
                    'discount': '10.00',
                },
                {
                    'product_id': None,
                    'is_custom': True,
                    'custom_description': 'Installation',
                    'quantity': 1,
                    'unit_price': '50.00',
                    'discount': '0.00',
                },
            ],
        }
        payload.update(overrides)
        return payload

    def post_update(self, payload):
        return self.client.post(
            self.update_url(),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def assert_quotation_unchanged(self):
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.title, 'Original quotation')
        self.assertEqual(self.quotation.subtotal, Decimal('200.00'))
        self.assertEqual(self.quotation.total_amount, Decimal('190.00'))
        self.assertEqual(list(self.quotation.items.values_list('pk', flat=True)), [self.original_item.pk])

    def test_edit_page_requires_login_and_change_permission(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.edit_url()).status_code, 302)

        user = User.objects.create_user(username='viewer', password='password')
        user.user_permissions.add(Permission.objects.get(codename='view_quotation'))
        self.client.force_login(user)
        response = self.client.get(self.edit_url())
        self.assertRedirects(response, reverse('core:unauthorized'))

    def test_update_api_denies_user_without_change_permission_as_json(self):
        self.editor.user_permissions.remove(Permission.objects.get(codename='change_quotation'))
        self.editor = User.objects.get(pk=self.editor.pk)
        response = self.post_update(self.payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')
        self.assert_quotation_unchanged()

    def test_edit_page_serializes_product_custom_and_removed_product_items(self):
        QuotationItem.objects.create(
            quotation=self.quotation,
            is_custom=True,
            custom_description='<b>Custom "service"</b>',
            quantity=1,
            unit_price=Decimal('40.00'),
        )
        removed = QuotationItem.objects.create(
            quotation=self.quotation,
            product=self.product,
            custom_description='Historical clock',
            quantity=1,
            unit_price=Decimal('25.00'),
        )
        self.product.delete()

        response = self.client.get(self.edit_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'quotations/quotation_form.html')
        initial = response.context['initial_data']
        self.assertEqual(initial['title'], 'Original quotation')
        self.assertEqual(initial['quotation_date'], '2026-08-20')
        custom = next(item for item in initial['items'] if item['is_custom'])
        self.assertEqual(custom['custom_description'], '<b>Custom "service"</b>')
        removed_data = next(
            item for item in initial['items']
            if item['product_id'] is None and item['display_name'] == 'Historical clock'
        )
        self.assertEqual(removed_data['display_name'], 'Historical clock')
        self.assertContains(response, 'quotationInitialData')
        self.assertNotContains(response, '<b>Custom "service"</b>', html=True)
        removed.refresh_from_db()
        self.assertIsNone(removed.product)

    def test_successful_update_replaces_items_and_preserves_identity_and_inventory(self):
        old_number = self.quotation.quotation_number
        response = self.post_update(self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Quotation updated successfully.')

        self.quotation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.quotation.quotation_number, old_number)
        self.assertEqual(self.quotation.status, Quotation.Status.SENT)
        self.assertEqual(self.quotation.created_by, self.creator)
        self.assertEqual(self.quotation.title, 'Updated quotation')
        self.assertEqual(self.quotation.subtotal, Decimal('400.00'))
        self.assertEqual(self.quotation.total_amount, Decimal('375.00'))
        self.assertEqual(self.quotation.items.count(), 2)
        self.assertFalse(self.quotation.items.filter(pk=self.original_item.pk).exists())
        self.assertEqual(self.product.total_stock, 7)

        audit = AuditLog.objects.get(model_name='Quotation', object_id=self.quotation.pk)
        self.assertEqual(audit.action, 'UPDATE')
        self.assertEqual(audit.changes['before']['total'], '190.00')
        self.assertEqual(audit.changes['after']['total'], '375.00')

    def test_update_normalizes_bad_prices_and_never_stores_negative_totals(self):
        payload = self.payload(
            discount='999.00',
            items=[{
                'product_id': 999999,
                'is_custom': False,
                'quantity': 'bad',
                'unit_price': 'bad',
                'discount': '-5',
            }],
        )
        response = self.post_update(payload)
        self.assertEqual(response.status_code, 200)
        self.quotation.refresh_from_db()
        item = self.quotation.items.get()
        self.assertIsNone(item.product)
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.unit_price, Decimal('0.00'))
        self.assertEqual(item.discount, Decimal('0.00'))
        self.assertEqual(self.quotation.total_amount, Decimal('0.00'))

    def test_invalid_payloads_do_not_mutate_quotation(self):
        cases = (
            self.payload(title=''),
            self.payload(items=[]),
            self.payload(quotation_date='not-a-date'),
            self.payload(items=['invalid']),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.post_update(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['status'], 'error')
                self.assert_quotation_unchanged()

        response = self.client.post(self.update_url(), data='{', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assert_quotation_unchanged()

    def test_item_creation_failure_rolls_back_header_and_item_deletion(self):
        with patch('apps.quotations.views.QuotationItem.objects.create', side_effect=RuntimeError):
            response = self.post_update(self.payload())
        self.assertEqual(response.status_code, 500)
        self.assert_quotation_unchanged()
        self.assertFalse(AuditLog.objects.exists())

    def test_create_endpoint_contract_and_audit_are_unchanged(self):
        response = self.client.post(
            reverse('quotations:api_quotation_save'),
            data=json.dumps(self.payload(title='Created quotation')),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['message'], 'Quotation saved successfully.')
        created = Quotation.objects.get(pk=response.json()['quotation_id'])
        self.assertEqual(created.created_by, self.editor)
        self.assertTrue(AuditLog.objects.filter(
            action='CREATE', model_name='Quotation', object_id=created.pk
        ).exists())

    def test_list_and_detail_show_edit_only_with_permission(self):
        list_response = self.client.get(reverse('quotations:quotation_list'))
        detail_response = self.client.get(reverse('quotations:quotation_detail', args=[self.quotation.pk]))
        self.assertContains(list_response, self.edit_url())
        self.assertContains(detail_response, self.edit_url(), count=2)

        self.editor.user_permissions.remove(Permission.objects.get(codename='change_quotation'))
        self.editor = User.objects.get(pk=self.editor.pk)
        self.assertNotContains(self.client.get(reverse('quotations:quotation_list')), self.edit_url())
        self.assertNotContains(
            self.client.get(reverse('quotations:quotation_detail', args=[self.quotation.pk])),
            self.edit_url(),
        )

    def test_detail_print_and_delete_still_work_after_update(self):
        self.assertEqual(self.post_update(self.payload()).status_code, 200)
        detail_url = reverse('quotations:quotation_detail', args=[self.quotation.pk])
        print_url = reverse('quotations:quotation_print', args=[self.quotation.pk])
        delete_url = reverse('quotations:quotation_delete', args=[self.quotation.pk])
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(self.client.get(print_url).status_code, 200)
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(Quotation.objects.filter(pk=self.quotation.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='DELETE', object_id=self.quotation.pk).exists())
