from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import TimeStampedModel


class Customer(TimeStampedModel):
    """Customer model for retail clock shop."""
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Financial tracking
    total_purchases = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Total amount of all purchases'
    )
    total_paid = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Total amount paid'
    )
    total_due = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0.00'),
        help_text='Outstanding balance'
    )
    
    credit_limit = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text='Maximum credit allowed'
    )
    
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def recalculate_balance(self):
        """Recalculate customer balance from sales and payments."""
        from apps.sales.models import Sale
        
        # Total from completed sales
        sales_total = Sale.objects.filter(
            customer=self,
            status='completed'
        ).aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        # Total payments
        payments_total = self.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        self.total_purchases = sales_total
        self.total_paid = payments_total
        self.total_due = sales_total - payments_total
        self.save(update_fields=['total_purchases', 'total_paid', 'total_due'])
    
    def get_purchase_history(self):
        """Get all purchases by this customer."""
        return self.sales.filter(status='completed').order_by('-sale_date')
    
    def get_payment_history(self):
        """Get all payments by this customer."""
        return self.payments.order_by('-payment_date')
    
    def get_unpaid_invoices(self):
        """Get invoices with outstanding balance."""
        return self.sales.filter(
            status='completed'
        ).exclude(
            payment_status='paid'
        ).order_by('sale_date')


class Payment(TimeStampedModel):
    """Payment record for tracking customer payments."""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_payment', 'Mobile Payment'),
        ('cheque', 'Cheque'),
    ]
    
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name='payments'
    )
    sale = models.ForeignKey(
        'sales.Sale', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payments',
        help_text='Specific invoice this payment is for (optional)'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash'
    )
    reference = models.CharField(
        max_length=100, blank=True,
        help_text='Transaction reference or cheque number'
    )
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, related_name='received_payments'
    )
    
    class Meta:
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"Payment of {self.amount} from {self.customer.name}"


class CustomerNote(TimeStampedModel):
    """Notes and communications with customer."""
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE,
        related_name='customer_notes'
    )
    note = models.TextField()
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note for {self.customer.name} - {self.created_at.strftime('%Y-%m-%d')}"
