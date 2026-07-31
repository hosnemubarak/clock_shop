from django import forms
from .models import Warehouse, StockTransfer


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
