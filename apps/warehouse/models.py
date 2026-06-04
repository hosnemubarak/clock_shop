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
        from apps.inventory.models import Batch
        return Batch.objects.filter(
            warehouse=self, 
            quantity__gt=0
        ).aggregate(
            total=models.Sum(models.F('quantity') * models.F('buy_price'))
        )['total'] or Decimal('0.00')
    
    def get_total_items(self):
        """Get total number of items in this warehouse."""
        from apps.inventory.models import Batch
        return Batch.objects.filter(
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
        from apps.inventory.models import Batch
        
        if self.status != 'pending':
            raise ValueError('Transfer is not pending')
        
        with transaction.atomic():
            for item in self.items.select_for_update():
                source_batch = Batch.objects.select_for_update().get(pk=item.source_batch_id)
                
                if source_batch.quantity < item.quantity:
                    raise ValueError(f'Insufficient stock in batch {source_batch.batch_number}')
                
                # Reduce source batch
                source_batch.quantity -= item.quantity
                source_batch.save()
                
                # Find existing batch in destination with same product and buy_price
                # Use filter().first() to avoid MultipleObjectsReturned error
                dest_batch = Batch.objects.filter(
                    product=source_batch.product,
                    warehouse=self.destination_warehouse,
                    buy_price=source_batch.buy_price,
                ).first()
                
                if dest_batch:
                    # Update existing batch
                    dest_batch.quantity += item.quantity
                    dest_batch.save()
                else:
                    # Create new batch in destination warehouse
                    import datetime
                    prefix = f"B{datetime.date.today().strftime('%Y%m%d')}"
                    last_batch = Batch.objects.filter(
                        batch_number__startswith=prefix
                    ).order_by('-batch_number').first()
                    if last_batch:
                        last_num = int(last_batch.batch_number[-4:])
                        new_batch_number = f"{prefix}{last_num + 1:04d}"
                    else:
                        new_batch_number = f"{prefix}0001"
                    
                    dest_batch = Batch.objects.create(
                        product=source_batch.product,
                        warehouse=self.destination_warehouse,
                        batch_number=new_batch_number,
                        buy_price=source_batch.buy_price,
                        purchase_date=source_batch.purchase_date,
                        initial_quantity=item.quantity,
                        quantity=item.quantity,
                        supplier=source_batch.supplier,
                        notes=f'Transferred from {self.source_warehouse.name} ({self.transfer_number})',
                    )
                
                item.destination_batch = dest_batch
                item.save()
                
                # Update product stock
                source_batch.product.update_total_stock()
            
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()


class StockTransferItem(TimeStampedModel):
    """Individual items in a stock transfer."""
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    source_batch = models.ForeignKey(
        'inventory.Batch', on_delete=models.PROTECT,
        related_name='transfer_out_items'
    )
    destination_batch = models.ForeignKey(
        'inventory.Batch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transfer_in_items'
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.source_batch.product.display_name} x {self.quantity}"
    
    @property
    def product(self):
        return self.source_batch.product
    
    @property
    def unit_cost(self):
        return self.source_batch.buy_price
    
    @property
    def total_cost(self):
        return self.quantity * self.source_batch.buy_price
