from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Sale

@receiver(post_save, sender=Sale)
@receiver(post_delete, sender=Sale)
def update_customer_balance_from_sale(sender, instance, **kwargs):
    """
    Update customer balance when a sale is created, updated, or deleted.
    Resolves tight coupling and manual updates in views.
    """
    if instance.customer_id:
        instance.customer.recalculate_balance()
