from django import forms
from .models import Product, Category, Brand, Batch, Purchase, PurchaseItem, StockOut
from apps.warehouse.models import Warehouse


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Wall Clocks'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Various styles of wall-mounted clocks'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Seiko'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Premium Japanese clock manufacturer'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['sku', 'name', 'category', 'brand', 'description', 
                  'default_selling_price', 'image', 'is_active']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CLK-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Classic Pendulum Clock'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Traditional wooden pendulum clock with hourly chime'}),
            'default_selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 299.99'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ['product', 'warehouse', 'buy_price', 'initial_quantity', 
                  'purchase_date', 'supplier', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'buy_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 150.00'}),
            'initial_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'e.g. 25'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ABC Clock Suppliers'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Invoice #12345'}),
        }
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.quantity = instance.initial_quantity
        if commit:
            instance.save()
            instance.product.update_total_stock()
        return instance


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'purchase_date', 'notes']
        widgets = {
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ABC Clock Distributors'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. PO #2024-001, Delivery via courier'}),
        }


class PurchaseItemForm(forms.Form):
    """Form for adding items to a purchase."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select product-select'})
    )
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'})
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


class StockAdjustmentForm(forms.Form):
    """Form for manual stock adjustments."""
    ADJUSTMENT_TYPES = [
        ('add', 'Add Stock'),
        ('remove', 'Remove Stock'),
    ]
    
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(quantity__gt=0),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )


class StockOutForm(forms.ModelForm):
    """Form for creating stock out records."""
    class Meta:
        model = StockOut
        fields = ['warehouse', 'reason', 'stockout_date', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'stockout_date': forms.DateTimeInput(attrs={
                'class': 'form-control', 
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Additional details about this stock out...'
            }),
        }
