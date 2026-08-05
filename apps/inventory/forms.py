from django import forms
from .models import Product, Category, Brand, Purchase, PurchaseItem, StockOut
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
    initial_stock = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Optional: e.g. 50'})
    )
    initial_cost_price = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Optional: Cost per unit'})
    )
    initial_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        required=False,
        empty_label="Select Warehouse",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    initial_stock_supplier = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ABC Distributors'})
    )
    initial_stock_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    initial_stock_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes...'})
    )

    class Meta:
        model = Product
        fields = ['sku', 'brand', 'category', 'description', 
                  'default_selling_price', 'is_active']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CLK-001'}),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Traditional wooden pendulum clock with hourly chime'}),
            'default_selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 299.99'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        initial_stock = cleaned_data.get('initial_stock')
        initial_warehouse = cleaned_data.get('initial_warehouse')
        initial_stock_supplier = cleaned_data.get('initial_stock_supplier')
        initial_stock_date = cleaned_data.get('initial_stock_date')
        
        if initial_stock:
            if not initial_warehouse:
                self.add_error('initial_warehouse', 'Warehouse is required when adding initial stock.')
            if not initial_stock_date:
                self.add_error('initial_stock_date', 'Stock Date is required when adding initial stock.')
            
        return cleaned_data





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
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'e.g. 10'})
    )
    unit_price = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 150.00'})
    )


class StockAdjustmentForm(forms.Form):
    """Form for manual stock adjustments."""
    ADJUSTMENT_TYPES = [
        ('add', 'Add Stock'),
        ('remove', 'Remove Stock'),
    ]
    
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'e.g. 5'})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'e.g. Damaged goods, inventory correction...'})
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
