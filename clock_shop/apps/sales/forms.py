from django import forms
from django.utils import timezone
from .models import Sale, SaleItem
from apps.customers.models import Customer
from apps.inventory.models import Product, Batch


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['customer', 'sale_date', 'discount_amount', 'tax_amount', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'sale_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'tax_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True)
        self.fields['customer'].required = False


class SaleItemForm(forms.Form):
    """Form for adding items to a sale with manual batch selection."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True, total_stock__gt=0),
        widget=forms.Select(attrs={'class': 'form-select product-select'})
    )
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(quantity__gt=0),
        widget=forms.Select(attrs={'class': 'form-select batch-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    unit_price = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    discount = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        quantity = cleaned_data.get('quantity')
        
        if batch and quantity:
            if quantity > batch.quantity:
                raise forms.ValidationError(
                    f'Requested quantity ({quantity}) exceeds available stock ({batch.quantity}) in batch {batch.batch_number}.'
                )
        
        return cleaned_data


class QuickSaleForm(forms.Form):
    """Simplified form for quick sales."""
    customer_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Walk-in Customer'})
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone (optional)'})
    )


class PaymentForm(forms.Form):
    """Form for recording payment against a sale."""
    amount = forms.DecimalField(
        min_value=0.01,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01'
        })
    )
    payment_method = forms.ChoiceField(
        choices=[
            ('cash', 'Cash'),
            ('card', 'Card'),
            ('bank_transfer', 'Bank Transfer'),
            ('mobile_payment', 'Mobile Payment'),
            ('cheque', 'Cheque'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference/Transaction ID'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
