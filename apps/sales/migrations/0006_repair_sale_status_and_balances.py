from decimal import Decimal

from django.db import migrations, models


ILLEGAL_STATUSES = ['paid', 'partial']


def repair(apps, schema_editor):
    """
    Repair financial aggregates corrupted by two historic bugs:

    1. The POS checkout path wrote 'paid'/'partial' into Sale.status, which are
       members of PaymentStatus, not Status. Every consumer filters on
       status='completed', so those sales vanished from customer balances,
       statements, unpaid-invoice lists and reports.
    2. Payment recording incremented Sale.paid_amount and the Customer balance
       fields in the view *after* the post_save signal had already recomputed
       them from the payment rows, double-counting each payment.

    Both are repaired by recomputing every derived field from its source rows,
    so this migration is idempotent.
    """
    Sale = apps.get_model('sales', 'Sale')
    Payment = apps.get_model('customers', 'Payment')
    Customer = apps.get_model('customers', 'Customer')

    Sale.objects.filter(status__in=ILLEGAL_STATUSES).update(status='completed')

    _repair_sales(Sale, Payment)
    _repair_customers(Customer, Sale)


def _repair_sales(Sale, Payment):
    paid_by_sale = {
        row['sale_id']: row['total']
        for row in Payment.objects.filter(sale__isnull=False)
        .values('sale_id')
        .annotate(total=models.Sum('amount'))
    }

    to_update = []
    for sale in Sale.objects.all().only('id', 'total_amount', 'paid_amount', 'payment_status'):
        paid = paid_by_sale.get(sale.id) or Decimal('0.00')
        if paid >= sale.total_amount:
            status = 'paid'
        elif paid > 0:
            status = 'partial'
        else:
            status = 'unpaid'

        if sale.paid_amount != paid or sale.payment_status != status:
            sale.paid_amount = paid
            sale.payment_status = status
            to_update.append(sale)

    if to_update:
        Sale.objects.bulk_update(to_update, ['paid_amount', 'payment_status'], batch_size=500)


def _repair_customers(Customer, Sale):
    purchases_by_customer = {
        row['customer_id']: row['total']
        for row in Sale.objects.filter(customer__isnull=False, status='completed')
        .values('customer_id')
        .annotate(total=models.Sum('total_amount'))
    }

    to_update = []
    for customer in Customer.objects.all().only(
        'id', 'total_purchases', 'total_paid', 'total_due'
    ):
        purchases = purchases_by_customer.get(customer.id) or Decimal('0.00')
        paid = customer.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        due = purchases - paid

        if (
            customer.total_purchases != purchases
            or customer.total_paid != paid
            or customer.total_due != due
        ):
            customer.total_purchases = purchases
            customer.total_paid = paid
            customer.total_due = due
            to_update.append(customer)

    if to_update:
        Customer.objects.bulk_update(
            to_update, ['total_purchases', 'total_paid', 'total_due'], batch_size=500
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0005_alter_sale_sale_date'),
        ('customers', '0004_alter_payment_customer'),
    ]

    operations = [
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
