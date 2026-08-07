from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Creates default groups and assigns appropriate permissions'

    def handle(self, *args, **options):
        # Base queries
        all_perms = Permission.objects.all()
        
        # 1. Cashier
        cashier_group, _ = Group.objects.get_or_create(name='Cashier')
        cashier_perms = Permission.objects.filter(
            content_type__app_label__in=['sales', 'customers', 'inventory', 'warehouse', 'quotations']
        ).exclude(codename__startswith='delete_')
        
        # Add basic core permissions
        dashboard_perm = Permission.objects.filter(codename='view_dashboard').first()
        if dashboard_perm:
            cashier_perms = list(cashier_perms) + [dashboard_perm]
            
        cashier_group.permissions.set(cashier_perms)
        self.stdout.write(self.style.SUCCESS('Successfully configured Cashier group.'))

        # 2. Manager
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        manager_perms = Permission.objects.filter(
            content_type__app_label__in=['sales', 'customers', 'inventory', 'warehouse', 'quotations']
        )
        
        report_perms = Permission.objects.filter(
            codename__in=[
                'view_dashboard', 'view_sales_report', 'view_profit_report', 
                'view_stock_report', 'view_transfer_report', 'view_dead_stock_report'
            ]
        )
        manager_group.permissions.set(list(manager_perms) + list(report_perms))
        self.stdout.write(self.style.SUCCESS('Successfully configured Manager group.'))

        # 3. Admin
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        admin_perms = Permission.objects.filter(
            content_type__app_label__in=[
                'sales', 'customers', 'inventory', 'warehouse', 'quotations', 'core', 'auth', 'sessions', 'admin', 'contenttypes'
            ]
        )
        admin_group.permissions.set(admin_perms)
        self.stdout.write(self.style.SUCCESS('Successfully configured Admin group.'))
        self.stdout.write(self.style.WARNING('Note: Admins should also be is_superuser=True for full django-admin access.'))
