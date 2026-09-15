from django.db import models, transaction as db_transaction, IntegrityError
from django.db.models import Sum
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal, ROUND_HALF_UP
from apps.core.models import TimeStampedModel


def quantize_amount(value):
    """Quantize a Decimal to 2 decimal places, ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# Number formats: short global running numbers (e.g. INV10001, RET10001).
# Legacy invoices used INV/YYYYMMDD/0000 numbers; both formats coexist
# safely because they can never be the same string.
INVOICE_NUMBER_FORMAT = 'INV{:05d}'
RETURN_NUMBER_FORMAT = 'RET{:05d}'


class DocumentSequence(models.Model):
    """
    Monotonic counter for document numbers (invoices, returns).

    Values are issued under a row lock (select_for_update) so concurrent
    creation attempts can never generate the same number.
    """
    KEY_CHOICES = [
        ('invoice', 'Invoice'),
        ('return', 'Return'),
    ]

    key = models.CharField(max_length=20, unique=True, choices=KEY_CHOICES)
    value = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Document Sequence'
        verbose_name_plural = 'Document Sequences'

    def __str__(self):
        return f'{self.get_key_display()}: {self.value}'

    @classmethod
    def next_value(cls, key):
        """Atomically increment and return the next value for a key."""
        with db_transaction.atomic():
            try:
                seq = cls.objects.select_for_update().get(key=key)
            except cls.DoesNotExist:
                try:
                    seq = cls.objects.create(key=key, value=0)
                except IntegrityError:
                    # A concurrent first-use created the row; lock it now
                    seq = cls.objects.select_for_update().get(key=key)
            seq.value += 1
            seq.save(update_fields=['value'])
            return seq.value


class Sale(TimeStampedModel):
    """Sale/Invoice record."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
    ]
    
    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.PROTECT,
        related_name='sales', null=True, blank=True
    )
    sale_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid'
    )
    
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
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    
    # Cost tracking for profit calculation
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='sales'
    )
    
    class Meta:
        ordering = ['-sale_date', '-created_at']
    
    def __str__(self):
        return f"{self.invoice_number}"
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = INVOICE_NUMBER_FORMAT.format(
                DocumentSequence.next_value('invoice')
            )
        super().save(*args, **kwargs)

    @property
    def due_amount(self):
        """Amount still due."""
        return self.total_amount - self.paid_amount
    
    @property
    def profit(self):
        """Calculate profit for this sale."""
        return self.total_amount - self.discount_amount - self.total_cost

    @property
    def total_quantity(self):
        """Total units sold across all items on this invoice."""
        return sum(item.quantity for item in self.items.all())

    def update_payment_status(self):
        """Update payment status based on paid amount."""
        if self.paid_amount >= self.total_amount:
            self.payment_status = 'paid'
        elif self.paid_amount > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'
        self.save(update_fields=['paid_amount', 'payment_status'])
    
    def calculate_totals(self):
        """Recalculate totals from items."""
        items = self.items.all()
        self.subtotal = sum(item.total_price for item in items)
        self.total_cost = sum(item.total_cost for item in items)
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount
        self.save(update_fields=['subtotal', 'total_cost', 'total_amount'])
    
    def recalculate_paid_amount(self):
        """Recalculate paid_amount from all linked payments."""
        from apps.customers.models import Payment
        total_paid = Payment.objects.filter(sale=self).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        self.paid_amount = total_paid
        self.update_payment_status()

    @property
    def total_returned_amount(self):
        """Total refund amount across completed returns."""
        return self.returns.filter(status='completed').aggregate(
            total=Sum('refund_amount')
        )['total'] or Decimal('0.00')

    @property
    def has_returns(self):
        """Whether this sale has any completed returns."""
        return self.returns.filter(status='completed').exists()

    def _returned_before(self, exclude_return=None):
        """Per-sale-item quantities returned by completed returns, excluding one return."""
        qs = SaleReturnItem.objects.filter(
            sale_item__sale=self,
            sale_return__status='completed',
        )
        if exclude_return is not None and exclude_return.pk:
            qs = qs.exclude(sale_return=exclude_return)
        return {
            row['sale_item']: row['total'] or 0
            for row in qs.values('sale_item').annotate(total=Sum('quantity'))
        }

    def recalculate_after_return(self, return_items, exclude_return=None):
        """
        Apply sale-level financial updates for a return using the
        proportion-of-remaining algorithm. Returns the refund amount.

        `return_items` are SaleReturnItem instances (saved, with price
        snapshots) belonging to a single return of this sale.
        """
        return_items = list(return_items)
        sale_items = list(self.items.all())
        already_before = self._returned_before(exclude_return=exclude_return)

        # Quantities being returned by this return, per sale item
        this_return_qty = {}
        for ri in return_items:
            this_return_qty[ri.sale_item_id] = (
                this_return_qty.get(ri.sale_item_id, 0) + ri.quantity
            )

        # Line figures from price snapshots
        line_gross = Decimal('0.00')
        item_discount_share = Decimal('0.00')
        returned_cost = Decimal('0.00')
        for ri in return_items:
            line_gross += ri.quantity * ri.unit_price
            if ri.sale_item.quantity > 0:
                item_discount_share += quantize_amount(
                    ri.sale_item.discount * ri.quantity / ri.sale_item.quantity
                )
            returned_cost += ri.quantity * ri.cost_price

        # Remaining gross value before this return (guard division by zero)
        remaining_gross_before = Decimal('0.00')
        for si in sale_items:
            remaining_gross_before += (
                (si.quantity - already_before.get(si.pk, 0)) * si.unit_price
            )

        if remaining_gross_before > 0:
            invoice_discount_share = quantize_amount(
                self.discount_amount * line_gross / remaining_gross_before
            )
            tax_share = quantize_amount(
                self.tax_amount * line_gross / remaining_gross_before
            )
        else:
            invoice_discount_share = Decimal('0.00')
            tax_share = Decimal('0.00')

        refund_amount = (
            line_gross - item_discount_share - invoice_discount_share + tax_share
        )

        # Full-return snap: every item fully returned -> zero totals, exact refund
        fully_returned = all(
            already_before.get(si.pk, 0) + this_return_qty.get(si.pk, 0) == si.quantity
            for si in sale_items
        )

        if fully_returned:
            refund_amount = self.total_amount
            self.subtotal = Decimal('0.00')
            self.discount_amount = Decimal('0.00')
            self.tax_amount = Decimal('0.00')
            self.total_amount = Decimal('0.00')
            self.total_cost = Decimal('0.00')
        else:
            refund_amount = min(refund_amount, self.total_amount)
            self.subtotal -= (line_gross - item_discount_share)
            self.discount_amount -= invoice_discount_share
            self.tax_amount -= tax_share
            self.total_cost -= returned_cost
            self.total_amount = self.subtotal - self.discount_amount + self.tax_amount

        self.save(update_fields=[
            'subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'total_cost',
        ])
        return quantize_amount(refund_amount)


class SaleItem(TimeStampedModel):
    """
    Individual items in a sale.
    Links directly to a batch for COGS tracking.
    Supports custom entries for old dues, legacy items, etc.
    """
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT,
        related_name='sale_items',
        null=True, blank=True  # Null for custom items
    )
    batch = models.ForeignKey(
        'inventory.Batch', on_delete=models.PROTECT,
        related_name='sale_items',
        help_text='Specific batch this item was sold from',
        null=True, blank=True  # Null for custom items
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Selling price per unit'
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Cost price from batch (for profit calculation)'
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00')
    )
    # Custom item fields
    is_custom = models.BooleanField(default=False, help_text='True for custom/manual entries')
    custom_description = models.CharField(
        max_length=255, blank=True,
        help_text='Description for custom items (old dues, legacy items, etc.)'
    )
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        if self.is_custom:
            return f"{self.custom_description} x {self.quantity}"
        return f"{self.product.display_name} x {self.quantity}" if self.product else f"Item x {self.quantity}"
    
    @property
    def total_price(self):
        """Total selling price."""
        return (self.quantity * self.unit_price) - self.discount
    
    @property
    def total_cost(self):
        """Total cost (COGS)."""
        return self.quantity * self.cost_price
    
    @property
    def profit(self):
        """Profit on this item."""
        return self.total_price - self.total_cost

    @property
    def returned_quantity(self):
        """Quantity of this item already returned (completed returns only)."""
        cached = getattr(self, '_returned_quantity_cache', None)
        if cached is not None:
            return cached
        return self.return_items.filter(
            sale_return__status='completed'
        ).aggregate(total=Sum('quantity'))['total'] or 0

    @property
    def returnable_quantity(self):
        """Quantity of this item that can still be returned."""
        return self.quantity - self.returned_quantity

    def save(self, *args, **kwargs):
        # Auto-set cost price from batch if not set
        if not self.cost_price and self.batch:
            self.cost_price = self.batch.buy_price
        super().save(*args, **kwargs)


class SaleReturn(TimeStampedModel):
    """Record of returned items from a sale."""
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    return_number = models.CharField(max_length=50, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    return_date = models.DateTimeField()
    reason = models.TextField()
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    payment_refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Portion of the refund that reverses payments already made '
                  '(over-paid amount handed back to the customer)'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='completed',
        help_text='Only completed returns affect stock and figures'
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='sale_returns'
    )

    class Meta:
        ordering = ['-return_date']

    def __str__(self):
        return f"{self.return_number} - {self.sale.invoice_number}"

    def save(self, *args, **kwargs):
        if not self.return_number:
            self.return_number = RETURN_NUMBER_FORMAT.format(
                DocumentSequence.next_value('return')
            )
        super().save(*args, **kwargs)

    def process_return(self):
        """
        Process this return atomically: re-validate quantities inside a
        lock, restore stock, apply financial updates (mirrors the
        StockOut.complete_stockout pattern).
        """
        from django.db import transaction
        from apps.inventory.models import Batch

        if self.status == 'cancelled':
            raise ValueError('Cannot process a cancelled return.')
        if self.pk and self.status == 'completed':
            raise ValueError('Return has already been processed.')

        with transaction.atomic():
            # Re-fetch the sale inside the lock; never trust the caller's instance
            sale = Sale.objects.select_for_update().get(pk=self.sale_id)
            self.sale = sale

            if sale.status != 'completed':
                raise ValidationError('Returns can only be created for completed sales.')

            return_items = list(
                self.items.select_related('sale_item', 'sale_item__product', 'sale_item__batch')
            )
            if not return_items:
                raise ValidationError('Return must contain at least one item.')

            # Re-validate every quantity inside the lock (race/duplicate protection)
            already_before = sale._returned_before(exclude_return=self)
            this_return_qty = {}
            for ri in return_items:
                sale_item = ri.sale_item
                if sale_item.sale_id != sale.pk:
                    raise ValidationError('Return item does not belong to this sale.')
                already = already_before.get(sale_item.pk, 0) + this_return_qty.get(sale_item.pk, 0)
                returnable = sale_item.quantity - already
                if ri.quantity < 1 or ri.quantity > returnable:
                    raise ValidationError(
                        f'Cannot return {ri.quantity} of "{sale_item}" '
                        f'(returnable: {returnable}).'
                    )
                this_return_qty[sale_item.pk] = this_return_qty.get(sale_item.pk, 0) + ri.quantity

            # Restore stock (skip custom items / items without a batch)
            for ri in return_items:
                sale_item = ri.sale_item
                if sale_item.is_custom or not sale_item.batch_id:
                    continue
                batch = Batch.objects.select_for_update().get(pk=sale_item.batch_id)
                batch.quantity += ri.quantity
                batch.save()
                if sale_item.product:
                    sale_item.product.update_total_stock()

            # Financial updates (proportion-of-remaining algorithm)
            total_before = sale.total_amount
            refund_amount = sale.recalculate_after_return(
                return_items, exclude_return=self
            )
            total_after = sale.total_amount

            # Portion of the refund that reverses payments already made:
            # when the return pushes the invoice past fully-paid, the
            # over-payment is refunded to the customer instead of becoming
            # credit against their other invoices. The telescoping formula
            # (cumulative over-payment after minus before) keeps sequential
            # returns exact: their payment refunds always sum to
            # max(0, paid_amount - final total_amount).
            paid = sale.paid_amount
            payment_refund = (
                max(Decimal('0.00'), paid - total_after)
                - max(Decimal('0.00'), paid - total_before)
            )
            self.refund_amount = refund_amount
            self.payment_refund_amount = payment_refund
            self.status = 'completed'
            self.save()

            # Customer balance recompute from source (walk-ins have no customer)
            if sale.customer:
                sale.customer.recalculate_balance()

            sale.update_payment_status()


class SaleReturnItem(TimeStampedModel):
    """Individual returned items."""
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='return_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Selling price per unit at time of return (snapshot)'
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Cost price per unit at time of return (snapshot)'
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        sale_item = self.sale_item
        if sale_item.is_custom or not sale_item.product:
            return f"{sale_item.custom_description or 'Custom Item'} x {self.quantity}"
        return f"{sale_item.product.display_name} x {self.quantity}"

    @property
    def line_total(self):
        """Gross line value (quantity x snapshot unit price)."""
        return self.quantity * self.unit_price
