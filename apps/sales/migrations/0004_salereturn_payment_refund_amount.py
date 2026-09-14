from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0003_sale_return_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='salereturn',
            name='payment_refund_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Portion of the refund that reverses payments already made (over-paid amount handed back to the customer)', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
    ]
