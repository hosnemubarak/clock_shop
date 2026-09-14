from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_saleitem_custom_description_saleitem_is_custom_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='salereturn',
            name='status',
            field=models.CharField(choices=[('completed', 'Completed'), ('cancelled', 'Cancelled')], default='completed', help_text='Only completed returns affect stock and figures', max_length=20),
        ),
        migrations.AddField(
            model_name='salereturn',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='salereturnitem',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Selling price per unit at time of return (snapshot)', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AddField(
            model_name='salereturnitem',
            name='cost_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Cost price per unit at time of return (snapshot)', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AlterField(
            model_name='salereturnitem',
            name='sale_item',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='return_items', to='sales.saleitem'),
        ),
    ]
