from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Creates default groups and assigns appropriate permissions'

    def handle(self, *args, **options):
        # 1. Cashier
        # Can create sales and register customers.
        cashier_group, _ = Group.objects.get_or_create(name='Cashier')
        cashier_permissions = Permission.objects.filter(
            content_type__app_label__in=['sales', 'customers', 'inventory', 'warehouse']
        ).exclude(
            codename__startswith='delete_'
        )
        cashier_group.permissions.set(cashier_permissions)
        self.stdout.write(self.style.SUCCESS('Successfully configured Cashier group.'))

        # 2. Manager
        # Can manage inventory, process returns, and view reports.
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        manager_permissions = Permission.objects.filter(
            content_type__app_label__in=['inventory', 'warehouse']
        )
        
        # Add returns permission for Manager
        return_permissions = Permission.objects.filter(
            content_type__app_label='sales',
            content_type__model__in=['salereturn', 'salereturnitem']
        )

        # Reports permissions (if any view permissions are needed for reports app or global viewing)
        reports_permissions = Permission.objects.filter(
            content_type__app_label='reports'
        )

        manager_group.permissions.set(list(manager_permissions) + list(return_permissions) + list(reports_permissions))
        self.stdout.write(self.style.SUCCESS('Successfully configured Manager group.'))

        # 3. Admin
        # View audit logs and manage staff (must be superuser).
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        admin_permissions = Permission.objects.filter(
            content_type__app_label='core',
            content_type__model='auditlog'
        )
        # Admin needs to manage staff
        staff_permissions = Permission.objects.filter(
            content_type__app_label='auth',
            content_type__model__in=['user', 'group']
        )
        admin_group.permissions.set(list(admin_permissions) + list(staff_permissions))
        self.stdout.write(self.style.SUCCESS('Successfully configured Admin group.'))
        self.stdout.write(self.style.WARNING('Note: Users assigned to Admin should also be marked as superuser (is_superuser=True) for full management access as per requirements.'))
