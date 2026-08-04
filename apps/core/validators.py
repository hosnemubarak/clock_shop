from django.core.validators import RegexValidator

bd_phone_validator = RegexValidator(
    regex=r'^(?:\+?88)?01[3-9]\d{8}$',
    message="Enter a valid Bangladeshi mobile number (e.g. 01712345678 or +8801712345678)."
)
