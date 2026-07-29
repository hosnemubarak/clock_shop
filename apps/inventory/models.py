from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel


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
    
    @property
    def dropdown_display(self):
        """Returns SKU + Brand Name for dropdown displays (same as display_name)."""
        return self.display_name
    
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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocks')
    warehouse = models.ForeignKey('warehouse.Warehouse', on_delete=models.CASCADE, related_name='product_stocks')
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
        if not self.purchase_number:
            import datetime
            prefix = f"PO{datetime.date.today().strftime('%Y%m%d')}"
            last = Purchase.objects.filter(
                purchase_number__startswith=prefix
            ).order_by('-purchase_number').first()
            if last:
                last_num = int(last.purchase_number[-4:])
                self.purchase_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.purchase_number = f"{prefix}0001"
        super().save(*args, **kwargs)


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
    REASON_CHOICES = [
        ('damage', 'Damaged'),
        ('loss', 'Lost/Theft'),
        ('expired', 'Expired'),
        ('internal', 'Internal Use'),
        ('adjustment', 'Stock Adjustment'),
        ('return_supplier', 'Return to Supplier'),
        ('sample', 'Sample/Display'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    stockout_number = models.CharField(max_length=50, unique=True)
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.PROTECT,
        related_name='stock_outs'
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
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
        if not self.stockout_number:
            import datetime
            prefix = f"OUT{datetime.date.today().strftime('%Y%m%d')}"
            last = StockOut.objects.filter(
                stockout_number__startswith=prefix
            ).order_by('-stockout_number').first()
            if last:
                last_num = int(last.stockout_number[-4:])
                self.stockout_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.stockout_number = f"{prefix}0001"
        super().save(*args, **kwargs)
    
    def complete_stockout(self):
        """Complete the stock out and reduce inventory."""
        from django.utils import timezone
        from django.db import transaction
        
        if self.status != 'pending':
            raise ValueError('Stock out is not pending')
        
        with transaction.atomic():
            total_value = Decimal('0.00')
            
            for item in self.items.select_for_update():
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
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()
    
    def cancel_stockout(self):
        """Cancel the stock out. If completed, restore stock."""
        from django.utils import timezone
        from django.db import transaction
        
        if self.status == 'cancelled':
            raise ValueError('Stock out is already cancelled')
        
        with transaction.atomic():
            if self.status == 'completed':
                # Restore stock for completed stock outs
                for item in self.items.all():
                    stock, created = ProductStock.objects.select_for_update().get_or_create(
                        product=item.product,
                        warehouse=self.warehouse,
                        defaults={'quantity': 0}
                    )
                    stock.quantity += item.quantity
                    stock.save()
                    item.product.update_total_stock()
            
            self.status = 'cancelled'
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
        return f"{self.product.display_name} x {self.quantity}"
    
    @property
    def total_cost(self):
        return self.quantity * self.cost_price
