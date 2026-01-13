from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel


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
            import datetime
            prefix = f"INV{datetime.date.today().strftime('%Y%m%d')}"
            last = Sale.objects.filter(
                invoice_number__startswith=prefix
            ).order_by('-invoice_number').first()
            if last:
                last_num = int(last.invoice_number[-4:])
                self.invoice_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.invoice_number = f"{prefix}0001"
        super().save(*args, **kwargs)
    
    @property
    def due_amount(self):
        """Amount still due."""
        return self.total_amount - self.paid_amount
    
    @property
    def profit(self):
        """Calculate profit for this sale."""
        return self.total_amount - self.discount_amount - self.total_cost
    
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
    
    def save(self, *args, **kwargs):
        # Auto-set cost price from batch if not set
        if not self.cost_price and self.batch:
            self.cost_price = self.batch.buy_price
        super().save(*args, **kwargs)


class SaleReturn(TimeStampedModel):
    """Record of returned items from a sale."""
    return_number = models.CharField(max_length=50, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    return_date = models.DateTimeField()
    reason = models.TextField()
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
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
            import datetime
            prefix = f"RET{datetime.date.today().strftime('%Y%m%d')}"
            last = SaleReturn.objects.filter(
                return_number__startswith=prefix
            ).order_by('-return_number').first()
            if last:
                last_num = int(last.return_number[-4:])
                self.return_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.return_number = f"{prefix}0001"
        super().save(*args, **kwargs)


class SaleReturnItem(TimeStampedModel):
    """Individual returned items."""
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.sale_item.product.display_name} x {self.quantity}"
