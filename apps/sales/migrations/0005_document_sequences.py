from django.db import migrations, models


def seed_sequences(apps, schema_editor):
    DocumentSequence = apps.get_model('sales', 'DocumentSequence')
    # Seed at 10000 so the first issued numbers are INV10001 / RET10001,
    # clearly distinguishable from legacy per-day counters
    DocumentSequence.objects.get_or_create(key='invoice', defaults={'value': 10000})
    DocumentSequence.objects.get_or_create(key='return', defaults={'value': 10000})


def unseed_sequences(apps, schema_editor):
    # Leave rows in place on reverse; existing document numbers stay valid
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0004_salereturn_payment_refund_amount'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('invoice', 'Invoice'), ('return', 'Return')], max_length=20, unique=True)),
                ('value', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Document Sequence',
                'verbose_name_plural': 'Document Sequences',
            },
        ),
        migrations.RunPython(seed_sequences, unseed_sequences),
    ]
