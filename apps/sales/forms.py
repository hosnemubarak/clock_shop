from django import forms
from django.utils import timezone
from .models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.inventory.models import Product
from apps.warehouse.models import Warehouse


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['customer', 'sale_date', 'discount_amount', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'sale_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Special instructions, customer notes...'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Empty queryset so the template doesn't render thousands of options.
        # TomSelect will fetch customers via AJAX.
        self.fields['customer'].queryset = Customer.objects.none()
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = "Walk-in Customer (None)"


class SaleItemForm(forms.Form):
    """Form for adding items to a sale with manual stock selection."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True, total_stock__gt=0),
        widget=forms.Select(attrs={'class': 'form-select product-select'})
    )
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select warehouse-select'})
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
        warehouse = cleaned_data.get('warehouse')
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        
        if warehouse and product and quantity:
            from apps.inventory.models import ProductStock
            stock = ProductStock.objects.filter(product=product, warehouse=warehouse).first()
            if not stock or quantity > stock.quantity:
                stock_qty = stock.quantity if stock else 0
                raise forms.ValidationError(
                    f'Requested quantity ({quantity}) exceeds available stock ({stock_qty}) in {warehouse.name}.'
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
        choices=Payment.PaymentMethod.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference/Transaction ID'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Any additional notes...'})
    )
