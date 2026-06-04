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
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    # Computed fields (updated via signals or methods)
    total_stock = models.PositiveIntegerField(default=0)
    
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
        """Update total stock from all batches."""
        self.total_stock = self.batches.filter(quantity__gt=0).aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
        self.save(update_fields=['total_stock'])
    
    def get_available_batches(self, warehouse=None):
        """Get batches with available stock."""
        batches = self.batches.filter(quantity__gt=0)
        if warehouse:
            batches = batches.filter(warehouse=warehouse)
        return batches.order_by('purchase_date')
    
    def get_average_cost(self):
        """Calculate weighted average cost from all batches."""
        batches = self.batches.filter(quantity__gt=0)
        total_value = sum(b.quantity * b.buy_price for b in batches)
        total_qty = sum(b.quantity for b in batches)
        if total_qty > 0:
            return total_value / total_qty
        return Decimal('0.00')


class Batch(TimeStampedModel):
    """
    Batch model for tracking purchases.
    Each purchase creates a new batch with its own buy price.
    """
    batch_number = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='batches')
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.PROTECT, 
        related_name='batches'
    )
    buy_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Purchase price per unit'
    )
    initial_quantity = models.PositiveIntegerField(help_text='Original quantity purchased')
    quantity = models.PositiveIntegerField(help_text='Current available quantity')
    purchase_date = models.DateField()
    supplier = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-purchase_date', '-created_at']
        verbose_name_plural = 'Batches'
    
    def __str__(self):
        return f"{self.batch_number} - {self.product.display_name} ({self.quantity} units)"
    
    def save(self, *args, **kwargs):
        if not self.batch_number:
            # Auto-generate batch number
            import datetime
            prefix = datetime.date.today().strftime('%Y%m%d')
            last_batch = Batch.objects.filter(
                batch_number__startswith=prefix
            ).order_by('-batch_number').first()
            if last_batch:
                last_num = int(last_batch.batch_number[-4:])
                self.batch_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.batch_number = f"{prefix}0001"
        super().save(*args, **kwargs)
    
    @property
    def total_value(self):
        """Total value of remaining stock."""
        return self.quantity * self.buy_price
    
    @property
    def sold_quantity(self):
        """Quantity that has been sold."""
        return self.initial_quantity - self.quantity


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
    batch = models.OneToOneField(Batch, on_delete=models.CASCADE, related_name='purchase_item')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
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
                batch = Batch.objects.select_for_update().get(pk=item.batch_id)
                
                if batch.quantity < item.quantity:
                    raise ValueError(f'Insufficient stock in batch {batch.batch_number}')
                
                # Reduce batch quantity
                batch.quantity -= item.quantity
                batch.save()
                
                # Calculate value
                item.cost_price = batch.buy_price
                item.save()
                total_value += item.quantity * batch.buy_price
                
                # Update product total stock
                batch.product.update_total_stock()
            
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
                    batch = Batch.objects.select_for_update().get(pk=item.batch_id)
                    batch.quantity += item.quantity
                    batch.save()
                    batch.product.update_total_stock()
            
            self.status = 'cancelled'
            self.save()
    
    @property
    def total_quantity(self):
        """Total quantity of items in this stock out."""
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0


class StockOutItem(TimeStampedModel):
    """Individual items in a stock out operation."""
    stockout = models.ForeignKey(StockOut, on_delete=models.CASCADE, related_name='items')
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name='stockout_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        help_text='Cost price per unit at time of stock out'
    )
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.batch.product.display_name} x {self.quantity}"
    
    @property
    def product(self):
        return self.batch.product
    
    @property
    def total_cost(self):
        return self.quantity * self.cost_price
