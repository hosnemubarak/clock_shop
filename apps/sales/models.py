import datetime
from django.db import models, transaction, IntegrityError
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel

from apps.core.utils import save_with_sequential_number

class Sale(TimeStampedModel):
    """Sale/Invoice record."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        
    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIAL = 'partial', 'Partially Paid'
        PAID = 'paid', 'Fully Paid'
    
    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.PROTECT,
        related_name='sales', null=True, blank=True
    )
    sale_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
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
        save_with_sequential_number(self, 'invoice_number', 'INV', *args, **kwargs)
    
    @property
    def due_amount(self):
        """Amount still due."""
        return self.total_amount - self.paid_amount
    
    @property
    def profit(self):
        """Calculate profit for this sale."""
        # calculate_totals() already nets discount_amount out of total_amount;
        # subtracting it again here under-reported margin on every discounted sale.
        return self.total_amount - self.total_cost
    
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
        # Query DB directly to bypass any stale prefetch cache (e.g. after returns)
        items = SaleItem.objects.filter(sale=self)
        self.subtotal = sum(item.total_price for item in items)
        self.total_cost = sum(item.total_cost for item in items)
        self.total_amount = self.subtotal - self.discount_amount
        self.save(update_fields=['subtotal', 'total_cost', 'total_amount'])
    
    def recalculate_paid_amount(self):
        """Recalculate paid_amount from linked payments, net of refunds.

        Refunds are not Payment rows (they live on SaleReturn.refund_amount), so
        this nets them out here. Without it, any later payment event on a
        returned sale would fire this recompute and reset paid_amount to the
        gross payments total, resurrecting the refunded cash and driving
        due_amount negative. Floored at zero.
        """
        from apps.customers.models import Payment
        total_paid = Payment.objects.filter(sale=self).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        refunds = self.returns.aggregate(
            total=models.Sum('refund_amount')
        )['total'] or Decimal('0.00')
        self.paid_amount = max(Decimal('0.00'), total_paid - refunds)
        self.update_payment_status()


class SaleItem(TimeStampedModel):
    """
    Individual items in a sale.
    Links directly to a product stock for COGS tracking.
    Supports custom entries for old dues, legacy items, etc.
    """
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT,
        related_name='sale_items',
        null=True, blank=True  # Null for custom items
    )
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.PROTECT,
        related_name='sale_items',
        help_text='Warehouse fulfilled from',
        null=True, blank=True
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    returned_quantity = models.PositiveIntegerField(
        default=0,
        help_text='Quantity returned so far'
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Selling price per unit'
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Cost price for profit calculation'
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
    def net_quantity(self):
        """Quantity net of returns."""
        return max(0, self.quantity - self.returned_quantity)

    @property
    def total_price(self):
        """Total selling price net of returns."""
        if self.quantity == 0:
            return Decimal('0.00')
        gross = (self.quantity * self.unit_price) - self.discount
        return (gross * Decimal(self.net_quantity) / Decimal(self.quantity)).quantize(Decimal('0.01'))
    
    @property
    def total_cost(self):
        """Total cost (COGS) net of returns."""
        return self.net_quantity * self.cost_price
    
    @property
    def profit(self):
        """Profit on this item."""
        return self.total_price - self.total_cost
    
    def save(self, *args, **kwargs):
        # Auto-set cost price from product average cost if not set
        if self.cost_price is None and self.product:
            self.cost_price = self.product.average_cost
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
        save_with_sequential_number(self, 'return_number', 'RET', *args, **kwargs)

    def restock_items(self):
        """Return each item's quantity to the warehouse it was sold from.

        Mirrors the stock-restore path in sale_cancel: locks the stock row,
        increments it, and refreshes the product's denormalized total. Custom
        line items (no product/warehouse) are skipped. Call inside an atomic
        block alongside creating the return and its items.
        """
        from apps.inventory.models import ProductStock

        for return_item in self.items.select_related('sale_item__product', 'sale_item__warehouse'):
            sale_item = return_item.sale_item
            if not sale_item.product or not sale_item.warehouse:
                continue
            stock, _ = ProductStock.objects.select_for_update().get_or_create(
                product=sale_item.product,
                warehouse=sale_item.warehouse,
                defaults={'quantity': 0},
            )
            stock.quantity += return_item.quantity
            stock.save(update_fields=['quantity'])
            sale_item.product.update_total_stock()
            
            # Update returned_quantity on the sale item for net calculations
            sale_item.returned_quantity += return_item.quantity
            sale_item.save(update_fields=['returned_quantity'])

    def returned_goods_value(self):
        """Value of the goods on this return, at their effective per-unit price.

        Each sale line's discount is spread evenly across its units, so a
        partial return only credits back its proportional share. This is the
        goods value to subtract from the sale total, independent of how much
        cash was actually refunded.
        """
        total = Decimal('0.00')
        for return_item in self.items.select_related('sale_item'):
            sale_item = return_item.sale_item
            if not sale_item.quantity:
                continue
            per_unit = sale_item.total_price / sale_item.quantity
            total += (per_unit * return_item.quantity).quantize(Decimal('0.01'))
        return total

    def returned_cost_value(self):
        """COGS of the returned units, so cost tracks the restocked inventory.

        The returned units go back into stock, so their cost must come off the
        sale's ``total_cost`` too; otherwise ``Sale.profit`` (total_amount -
        total_cost) and the sales-report margin understate profit by the
        returned units' cost.
        """
        total = Decimal('0.00')
        for return_item in self.items.select_related('sale_item'):
            sale_item = return_item.sale_item
            total += (sale_item.cost_price * return_item.quantity).quantize(Decimal('0.01'))
        return total

    def reconcile_sale_ledger(self):
        """Move the sale's money to reflect this return.

        A return reduces the sale's net items, so we just recalculate the sale totals.
        Cash handed back leaves the drawer -> reduce ``paid_amount`` by the actual ``refund_amount``.
        All are floored at zero so a return can never push the sale negative.
        Saving the sale fires the post_save signal that recomputes the customer balance.
        Call inside the same atomic block as the return creation and restock.
        """
        sale = self.sale
        sale.paid_amount = max(Decimal('0.00'), sale.paid_amount - self.refund_amount)
        sale.calculate_totals()  # Automatically computes based on net_quantity
        sale.update_payment_status()  # saves paid_amount + payment_status


class SaleReturnItem(TimeStampedModel):
    """Individual returned items."""
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        if self.sale_item.is_custom:
            return f"{self.sale_item.custom_description} x {self.quantity}"
        return f"{self.sale_item.product.display_name} x {self.quantity}"
