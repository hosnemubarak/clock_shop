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
    name = models.CharField(max_length=200)
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
        ordering = ['name']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"
    
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
        return f"{self.batch_number} - {self.product.name} ({self.quantity} units)"
    
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
        return f"{self.product.name} x {self.quantity}"
    
    @property
    def total_price(self):
        return self.quantity * self.unit_price
