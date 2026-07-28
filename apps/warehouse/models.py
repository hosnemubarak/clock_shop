from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel


class Warehouse(TimeStampedModel):
    """Warehouse/Shop location for stock management."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_shop = models.BooleanField(default=False, help_text='Is this a retail shop location?')
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def get_total_stock_value(self):
        """Calculate total value of stock in this warehouse."""
        from apps.inventory.models import ProductStock
        stocks = ProductStock.objects.filter(
            warehouse=self, 
            quantity__gt=0
        ).select_related('product')
        return sum(stock.quantity * stock.product.average_cost for stock in stocks) or Decimal('0.00')
    
    def get_total_items(self):
        """Get total number of items in this warehouse."""
        from apps.inventory.models import ProductStock
        return ProductStock.objects.filter(
            warehouse=self,
            quantity__gt=0
        ).aggregate(total=models.Sum('quantity'))['total'] or 0


class StockTransfer(TimeStampedModel):
    """Record of stock transfers between warehouses."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    transfer_number = models.CharField(max_length=50, unique=True)
    source_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, 
        related_name='transfers_out'
    )
    destination_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT,
        related_name='transfers_in'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transfer_date = models.DateTimeField()
    completed_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='stock_transfers'
    )
    
    class Meta:
        ordering = ['-transfer_date']
    
    def __str__(self):
        return f"{self.transfer_number}: {self.source_warehouse.code} → {self.destination_warehouse.code}"
    
    def save(self, *args, **kwargs):
        if not self.transfer_number:
            import datetime
            prefix = f"TRF{datetime.date.today().strftime('%Y%m%d')}"
            last = StockTransfer.objects.filter(
                transfer_number__startswith=prefix
            ).order_by('-transfer_number').first()
            if last:
                last_num = int(last.transfer_number[-4:])
                self.transfer_number = f"{prefix}{last_num + 1:04d}"
            else:
                self.transfer_number = f"{prefix}0001"
        super().save(*args, **kwargs)
    
    def complete_transfer(self):
        """Complete the transfer and move stock."""
        from django.utils import timezone
        from django.db import transaction
        from apps.inventory.models import ProductStock
        
        if self.status != 'pending':
            raise ValueError('Transfer is not pending')
        
        with transaction.atomic():
            for item in self.items.select_for_update():
                # Get source stock
                source_stock = ProductStock.objects.select_for_update().get(
                    product=item.product,
                    warehouse=self.source_warehouse
                )
                
                if source_stock.quantity < item.quantity:
                    raise ValueError(f'Insufficient stock for {item.product.display_name} in {self.source_warehouse.name}')
                
                # Reduce source stock
                source_stock.quantity -= item.quantity
                source_stock.save()
                
                # Add to destination stock
                dest_stock, created = ProductStock.objects.select_for_update().get_or_create(
                    product=item.product,
                    warehouse=self.destination_warehouse,
                    defaults={'quantity': 0}
                )
                dest_stock.quantity += item.quantity
                dest_stock.save()
                
                # Update product stock
                item.product.update_total_stock()
            
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()


class StockTransferItem(TimeStampedModel):
    """Individual items in a stock transfer."""
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'inventory.Product', on_delete=models.PROTECT,
        related_name='transfer_items', null=True, blank=True
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.product.display_name} x {self.quantity}"
    
    @property
    def unit_cost(self):
        return self.product.average_cost
    
    @property
    def total_cost(self):
        return self.quantity * self.product.average_cost
