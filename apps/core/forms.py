from django import forms
from .models import SystemSettings


class SystemSettingsForm(forms.ModelForm):
    """Form for managing system settings."""
    
    class Meta:
        model = SystemSettings
        fields = [
            'shop_name',
            'currency_symbol',
            'license_expiry_date',
            'low_stock_threshold',
            'alert_days_before_expiry',
        ]
        widgets = {
            'shop_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter shop name'
            }),
            'currency_symbol': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '৳'
            }),
            'license_expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'low_stock_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '5'
            }),
            'alert_days_before_expiry': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '30'
            }),
        }
        labels = {
            'shop_name': 'Shop Name',
            'currency_symbol': 'Currency Symbol',
            'license_expiry_date': 'License/Server Expiry Date',
            'low_stock_threshold': 'Low Stock Threshold',
            'alert_days_before_expiry': 'Alert Days Before Expiry',
        }
        help_texts = {
            'shop_name': 'Leave blank to use environment variable (SHOP_NAME)',
            'currency_symbol': 'Symbol displayed before prices',
            'license_expiry_date': 'Date when server/license expires',
            'low_stock_threshold': 'Products at or below this stock level are flagged as low stock',
            'alert_days_before_expiry': 'Show dashboard alert this many days before expiry',
        }
    
    def clean_low_stock_threshold(self):
        value = self.cleaned_data.get('low_stock_threshold')
        if value is not None and value < 1:
            raise forms.ValidationError('Threshold must be at least 1')
        return value
    
    def clean_alert_days_before_expiry(self):
        value = self.cleaned_data.get('alert_days_before_expiry')
        if value is not None and value < 1:
            raise forms.ValidationError('Alert days must be at least 1')
        return value
