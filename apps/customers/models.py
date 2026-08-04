from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.validators import bd_phone_validator


class Customer(TimeStampedModel):
    """Customer model for retail clock shop."""
    name = models.CharField(max_length=200, db_index=True)
    phone = models.CharField(
        validators=[bd_phone_validator], 
        max_length=20, 
        unique=True,
        error_messages={'unique': 'A customer with this phone number already exists.'}
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=['email'],
                name='unique_customer_email',
                condition=~Q(email=''),
                violation_error_message='A customer with this email already exists.'
            ),
        ]
    
    def __str__(self):
        if self.phone:
            return f"{self.name} - {self.phone}"
        return self.name
    
    def clean(self):
        """Validate uniqueness of email."""
        super().clean()
        if self.email:
            existing = Customer.objects.filter(email=self.email).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({'email': 'A customer with this email already exists.'})
    
    def recalculate_balance(self):
        """Recalculate customer balance from sales, payments and refunds.

        Balance is ``purchases - net cash``. A sale return reduces the sale's
        ``total_amount`` (fewer goods owed for) and refunds cash, so a refund is
        netted out of payments here: net cash = payments - refunds. Without the
        refund term a refunded customer would look overpaid, because the cash
        that left the drawer is not represented in the Payment rows.
        """
        from apps.sales.models import Sale, SaleReturn

        # Total from completed sales (already net of returned goods value).
        sales_total = Sale.objects.filter(
            customer=self,
            status='completed'
        ).aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0.00')

        # Total payments received.
        payments_total = self.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        # Cash refunded on returns against this customer's completed sales.
        refunds_total = SaleReturn.objects.filter(
            sale__customer=self,
            sale__status='completed'
        ).aggregate(
            total=models.Sum('refund_amount')
        )['total'] or Decimal('0.00')

        net_paid = payments_total - refunds_total
        self.total_purchases = sales_total
        self.total_paid = net_paid
        self.total_due = sales_total - net_paid
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
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        MOBILE_PAYMENT = 'mobile_payment', 'Mobile Payment'
        CHEQUE = 'cheque', 'Cheque'

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name='payments',
        null=True, blank=True
    )
    sale = models.ForeignKey(
        'sales.Sale', on_delete=models.PROTECT,
        null=True, blank=True, related_name='payments',
        help_text='Specific invoice this payment is for (optional)'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateTimeField(auto_now_add=True, db_index=True)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
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
        customer_name = self.customer.name if self.customer else 'Walk-in'
        return f"Payment of {self.amount} from {customer_name}"


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
