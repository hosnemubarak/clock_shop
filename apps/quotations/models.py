from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.utils import save_with_sequential_number


class Quotation(TimeStampedModel):
    """Quotation record — completely independent of Sales, Customers, and Inventory."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        EXPIRED = 'expired', 'Expired'

    quotation_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(
        max_length=255,
        help_text='Quotation name or title (e.g. "Office Clocks for ABC Ltd")'
    )
    quotation_date = models.DateField(db_index=True)
    valid_until = models.DateField(
        null=True, blank=True,
        help_text='Quotation validity/expiry date'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    # Client info — plain text, NOT linked to Customer model
    client_name = models.CharField(max_length=255, blank=True)
    client_phone = models.CharField(max_length=20, blank=True)
    client_address = models.TextField(blank=True)

    # Amounts
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='quotations'
    )

    class Meta:
        ordering = ['-quotation_date', '-created_at']
        permissions = [
            ("view_quotation_report", "Can view quotation reports"),
        ]

    def __str__(self):
        return f"{self.quotation_number} — {self.title}"

    def save(self, *args, **kwargs):
        save_with_sequential_number(self, 'quotation_number', 'QTN', *args, **kwargs)

    def calculate_totals(self):
        """Recalculate totals from items."""
        items = QuotationItem.objects.filter(quotation=self)
        self.subtotal = sum(item.total_price for item in items)
        self.total_amount = self.subtotal - self.discount_amount
        self.save(update_fields=['subtotal', 'total_amount'])


class QuotationItem(TimeStampedModel):
    """
    Individual line item in a quotation.
    Can reference a product (for display/pricing only) or be a custom entry.
    NO impact on inventory or stock.
    """
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.SET_NULL,
        related_name='quotation_items',
        null=True, blank=True,
        help_text='Optional reference for display only — no stock impact'
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Quoted price per unit'
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )

    # Custom item fields
    is_custom = models.BooleanField(
        default=False, help_text='True for custom/manual entries'
    )
    custom_description = models.CharField(
        max_length=255, blank=True,
        help_text='Description for custom items not in the product database'
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        if self.is_custom:
            return f"{self.custom_description} x {self.quantity}"
        return f"{self.product.display_name} x {self.quantity}" if self.product else f"Item x {self.quantity}"

    @property
    def total_price(self):
        """Total price for this line item."""
        return (self.quantity * self.unit_price) - self.discount
