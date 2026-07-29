import datetime
from django.db import models, transaction, IntegrityError
from django.core.validators import MinValueValidator
from django.db.models import Sum, F
from django.utils import timezone
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.utils import save_with_sequential_number


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
        
    def set_as_shop(self):
        """Set this warehouse as the primary shop and unset others."""
        with transaction.atomic():
            Warehouse.objects.exclude(pk=self.pk).update(is_shop=False)
            self.is_shop = True
            self.save(update_fields=['is_shop'])
    
    def get_total_stock_value(self):
        """Calculate total value of stock in this warehouse."""
        from apps.inventory.models import ProductStock
        result = ProductStock.objects.filter(
            warehouse=self, 
            quantity__gt=0
        ).aggregate(total=Sum(F('quantity') * F('product__average_cost')))
        return result['total'] or Decimal('0.00')
    
    def get_total_items(self):
        """Get total number of items in this warehouse."""
        from apps.inventory.models import ProductStock
        return ProductStock.objects.filter(
            warehouse=self,
            quantity__gt=0
        ).aggregate(total=Sum('quantity'))['total'] or 0


class StockTransfer(TimeStampedModel):
    """Record of stock transfers between warehouses."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    transfer_number = models.CharField(max_length=50, unique=True)
    source_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, 
        related_name='transfers_out'
    )
    destination_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT,
        related_name='transfers_in'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
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
        save_with_sequential_number(self, 'transfer_number', 'TRF', *args, **kwargs)
    
    def complete_transfer(self):
        """Complete the transfer and move stock."""
        from apps.inventory.models import ProductStock
        
        if self.status != 'pending':
            raise ValueError('Transfer is not pending')
        
        with transaction.atomic():
            for item in self.items.order_by('product_id').select_for_update():
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
