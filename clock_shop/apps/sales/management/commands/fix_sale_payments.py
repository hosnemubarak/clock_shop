from django.core.management.base import BaseCommand
from apps.sales.models import Sale


class Command(BaseCommand):
    help = 'Recalculate paid_amount for all sales from linked payments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sale-id',
            type=int,
            help='Fix a specific sale by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        sale_id = options.get('sale_id')
        dry_run = options.get('dry_run', False)
        
        if sale_id:
            sales = Sale.objects.filter(pk=sale_id)
        else:
            sales = Sale.objects.all()
        
        fixed_count = 0
        
        for sale in sales:
            # Calculate actual paid amount from payments
            from apps.customers.models import Payment
            from django.db.models import Sum
            from decimal import Decimal
            
            actual_paid = Payment.objects.filter(sale=sale).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            if sale.paid_amount != actual_paid:
                old_paid = sale.paid_amount
                old_status = sale.payment_status
                
                if dry_run:
                    self.stdout.write(
                        f"Would fix {sale.invoice_number}: "
                        f"paid_amount {old_paid} -> {actual_paid}"
                    )
                else:
                    sale.paid_amount = actual_paid
                    sale.update_payment_status()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Fixed {sale.invoice_number}: "
                            f"paid_amount {old_paid} -> {actual_paid}, "
                            f"status {old_status} -> {sale.payment_status}"
                        )
                    )
                fixed_count += 1
        
        if dry_run:
            self.stdout.write(f"\nDry run: {fixed_count} sale(s) would be fixed")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nFixed {fixed_count} sale(s)")
            )
