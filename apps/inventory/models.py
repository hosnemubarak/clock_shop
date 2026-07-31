from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.utils import save_with_sequential_number


class Category(TimeStampedModel):
    """Product category for clocks."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    """Clock brand/manufacturer."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    """Product model for clocks and related items."""
    sku = models.CharField(max_length=50, unique=True, verbose_name='SKU')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products', null=True, blank=True)
    description = models.TextField(blank=True)
    default_selling_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_active = models.BooleanField(default=True)
    
    # Computed fields (updated via signals or methods)
    total_stock = models.PositiveIntegerField(default=0)
    average_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    class Meta:
        ordering = ['sku']
    
    def __str__(self):
        return self.display_name
    
    @property
    def display_name(self):
        """Returns SKU + Brand Name as the product identifier."""
        if self.brand:
            return f"{self.sku} - {self.brand.name}"
        return self.sku
    
    def update_total_stock(self):
        """Update total stock from all warehouse stocks."""
        self.total_stock = self.stocks.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
        self.save(update_fields=['total_stock'])
        
    def recalculate_average_cost(self, new_qty, new_price):
        """Recalculate average cost when new stock is added."""
        total_value = (self.total_stock * self.average_cost) + (Decimal(new_qty) * Decimal(new_price))
        new_total_qty = self.total_stock + new_qty
        if new_total_qty > 0:
            self.average_cost = total_value / new_total_qty
            self.save(update_fields=['average_cost'])


class ProductStock(TimeStampedModel):
    """Tracks quantity of a product in a specific warehouse."""
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stocks')
    warehouse = models.ForeignKey('warehouse.Warehouse', on_delete=models.PROTECT, related_name='product_stocks')
    quantity = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ('product', 'warehouse')
        verbose_name_plural = 'Product Stocks'
        
    def __str__(self):
        return f"{self.product.display_name} in {self.warehouse.code} ({self.quantity})"

    @property
    def total_value(self):
        return Decimal(self.quantity) * self.product.average_cost


class Purchase(TimeStampedModel):
    """Purchase order record."""
    purchase_number = models.CharField(max_length=50, unique=True)
    supplier = models.CharField(max_length=200)
    purchase_date = models.DateField()
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, 
        null=True, related_name='purchases'
    )
    
    class Meta:
        ordering = ['-purchase_date', '-created_at']
    
    def __str__(self):
        return f"{self.purchase_number} - {self.supplier}"
    
    def save(self, *args, **kwargs):
        save_with_sequential_number(self, 'purchase_number', 'PO', *args, **kwargs)


class PurchaseItem(TimeStampedModel):
    """Individual items in a purchase order."""
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    warehouse = models.ForeignKey('warehouse.Warehouse', on_delete=models.PROTECT, related_name='purchase_items', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.product.display_name} x {self.quantity}"
    
    @property
    def total_price(self):
        return self.quantity * self.unit_price


class StockOut(TimeStampedModel):
    """
    Stock Out record for non-sale inventory reductions.
    Used for damage, loss, expired goods, internal use, adjustments, etc.
    """
    class Reason(models.TextChoices):
        DAMAGE = 'damage', 'Damaged'
        LOSS = 'loss', 'Lost/Theft'
        EXPIRED = 'expired', 'Expired'
        INTERNAL = 'internal', 'Internal Use'
        ADJUSTMENT = 'adjustment', 'Stock Adjustment'
        RETURN_SUPPLIER = 'return_supplier', 'Return to Supplier'
        SAMPLE = 'sample', 'Sample/Display'
        OTHER = 'other', 'Other'
        
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    stockout_number = models.CharField(max_length=50, unique=True)
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.PROTECT,
        related_name='stock_outs'
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    stockout_date = models.DateTimeField()
    completed_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text='Additional details about the stock out')
    total_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total value of stock removed (at cost price)'
    )
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='stock_outs'
    )
    
    class Meta:
        ordering = ['-stockout_date', '-created_at']
        verbose_name = 'Stock Out'
        verbose_name_plural = 'Stock Outs'
    
    def __str__(self):
        return f"{self.stockout_number} - {self.get_reason_display()}"
    
    def save(self, *args, **kwargs):
        save_with_sequential_number(self, 'stockout_number', 'OUT', *args, **kwargs)
    
    def complete_stockout(self):
        """Complete the stock out and reduce inventory."""
        if self.status != self.Status.PENDING:
            raise ValueError('Stock out is not pending')
        
        with transaction.atomic():
            total_value = Decimal('0.00')
            
            for item in self.items.order_by('product_id').select_for_update():
                stock, created = ProductStock.objects.select_for_update().get_or_create(
                    product=item.product,
                    warehouse=self.warehouse,
                    defaults={'quantity': 0}
                )
                
                if stock.quantity < item.quantity:
                    raise ValueError(f'Insufficient stock for {item.product.display_name}')
                
                # Reduce quantity
                stock.quantity -= item.quantity
                stock.save()
                
                # Calculate value using average_cost
                item.cost_price = item.product.average_cost
                item.save()
                total_value += item.quantity * item.cost_price
                
                # Update product total stock
                item.product.update_total_stock()
            
            self.total_value = total_value
            self.status = self.Status.COMPLETED
            self.completed_date = timezone.now()
            self.save()
    
    def cancel_stockout(self):
        """Cancel the stock out. If completed, restore stock."""
        if self.status == self.Status.CANCELLED:
            raise ValueError('Stock out is already cancelled')
        
        with transaction.atomic():
            if self.status == self.Status.COMPLETED:
                # Restore stock for completed stock outs. Iterate in product order
                # so this cannot deadlock against complete_stockout(), which locks
                # the same rows in the same order.
                for item in self.items.select_related('product').order_by('product_id'):
                    stock, created = ProductStock.objects.select_for_update().get_or_create(
                        product=item.product,
                        warehouse=self.warehouse,
                        defaults={'quantity': 0}
                    )
                    stock.quantity += item.quantity
                    stock.save()
                    item.product.update_total_stock()
            
            self.status = self.Status.CANCELLED
            self.save()
    
    @property
    def total_quantity(self):
        """Total quantity of items in this stock out."""
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0


class StockOutItem(TimeStampedModel):
    """Individual items in a stock out operation."""
    stockout = models.ForeignKey(StockOut, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stockout_items', null=True, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        help_text='Cost price per unit at time of stock out (Avg Cost)'
    )
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        # product is nullable, so guard the dereference: a row whose product was
        # cleared used to raise AttributeError in the admin and in error messages.
        name = self.product.display_name if self.product else '(deleted product)'
        return f"{name} x {self.quantity}"

    @property
    def total_cost(self):
        return self.quantity * self.cost_price
