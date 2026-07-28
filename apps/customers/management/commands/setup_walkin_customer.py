from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError

class Command(BaseCommand):
    help = 'Creates the default Walk-In Customer if it does not exist.'

    def handle(self, *args, **kwargs):
        try:
            from apps.customers.models import Customer
            
            # Use get_or_create to safely handle existing records
            customer, created = Customer.objects.get_or_create(
                phone='0000000000',
                defaults={
                    'name': 'Walk-In Customer',
                    'email': 'walkin@example.com',
                    'address': 'N/A'
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS('Successfully created generic "Walk-In Customer".'))
            else:
                self.stdout.write(self.style.WARNING('Generic "Walk-In Customer" already exists. No action taken.'))
                
        except (OperationalError, ProgrammingError) as e:
            self.stdout.write(self.style.ERROR(
                f'Database error occurred: {str(e)}\n'
                f'This usually means the database has not been fully migrated yet. '
                f'Please run "python manage.py migrate" first.'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An unexpected error occurred: {str(e)}'))
