from django import forms
from django.contrib.auth.models import User, Group
from .models import SystemSettings


class SystemSettingsForm(forms.ModelForm):
    """Form for managing system settings."""
    
    class Meta:
        model = SystemSettings
        fields = [
            'shop_name',
            'shop_address',
            'currency_symbol',
            'license_expiry_date',
            'low_stock_threshold',
            'alert_days_before_expiry',
            'allow_walkin_customers',
            'avg_cost_visibility',
        ]
        widgets = {
            'shop_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter shop name'
            }),
            'shop_address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full shop address',
                'rows': 3
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
            'allow_walkin_customers': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'avg_cost_visibility': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        labels = {
            'shop_name': 'Shop Name',
            'shop_address': 'Shop Address',
            'currency_symbol': 'Currency Symbol',
            'license_expiry_date': 'License/Server Expiry Date',
            'low_stock_threshold': 'Low Stock Threshold',
            'alert_days_before_expiry': 'Alert Days Before Expiry',
            'allow_walkin_customers': 'Allow Walk-in Customers',
        }
        help_texts = {
            'shop_name': 'Leave blank to use environment variable (SHOP_NAME)',
            'shop_address': 'Address printed on invoices and reports',
            'currency_symbol': 'Symbol displayed before prices',
            'license_expiry_date': 'Date when server/license expires',
            'low_stock_threshold': 'Products at or below this stock level are flagged as low stock',
            'alert_days_before_expiry': 'Show dashboard alert this many days before expiry',
            'allow_walkin_customers': 'Allow sales without requiring a registered customer profile',
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


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile."""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
        }


from django.contrib.auth.forms import PasswordChangeForm

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class StaffCreationForm(forms.ModelForm):
    """Form for creating a new staff member."""
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="Select a Role"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        required=True
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        
        # New staff are active by default
        user.is_active = True
        
        # If the selected role is Admin, they are a superuser
        role = self.cleaned_data['role']
        if role.name.lower() == 'admin':
            user.is_superuser = True
            user.is_staff = True
        elif role.name.lower() in ['manager', 'cashier']:
            user.is_staff = True
            
        if commit:
            user.save()
            user.groups.add(role)
        return user


