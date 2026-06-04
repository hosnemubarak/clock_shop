from django import forms
from django.utils import timezone
from .models import Warehouse, StockTransfer, StockTransferItem
from apps.inventory.models import Batch


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'code', 'address', 'phone', 'is_active', 'is_shop']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Main Store'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. WH001'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. 123 Main Street, City'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +1 555-123-4567'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_shop': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['source_warehouse', 'destination_warehouse', 'transfer_date', 'notes']
        widgets = {
            'source_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'destination_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'transfer_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g. Reason for transfer...'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['source_warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        self.fields['destination_warehouse'].queryset = Warehouse.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source_warehouse')
        destination = cleaned_data.get('destination_warehouse')
        
        if source and destination and source == destination:
            raise forms.ValidationError('Source and destination warehouses must be different.')
        
        return cleaned_data


class StockTransferItemForm(forms.Form):
    """Form for adding items to a transfer."""
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(quantity__gt=0),
        widget=forms.Select(attrs={'class': 'form-select batch-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'e.g. 10'})
    )
    
    def __init__(self, *args, source_warehouse=None, **kwargs):
        super().__init__(*args, **kwargs)
        if source_warehouse:
            self.fields['batch'].queryset = Batch.objects.filter(
                warehouse=source_warehouse,
                quantity__gt=0
            ).select_related('product')
    
    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        quantity = cleaned_data.get('quantity')
        
        if batch and quantity:
            if quantity > batch.quantity:
                raise forms.ValidationError(
                    f'Requested quantity ({quantity}) exceeds available stock ({batch.quantity}).'
                )
        
        return cleaned_data
