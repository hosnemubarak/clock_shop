from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_auditlog_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='shop_address',
            field=models.TextField(blank=True, default='', help_text='Shop address displayed on printed invoices'),
        ),
    ]
