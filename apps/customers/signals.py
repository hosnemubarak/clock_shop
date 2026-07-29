from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment

@receiver(post_save, sender=Payment)
@receiver(post_delete, sender=Payment)
def update_sale_and_customer_from_payment(sender, instance, **kwargs):
    """
    Update the related sale's paid amount and customer balance when a payment is created, updated, or deleted.
    Resolves tight coupling between customers app and sales app.
    """
    if instance.sale_id:
        instance.sale.recalculate_paid_amount()
        
    # Recalculate balance for the customer linked to the payment, or the sale's customer
    customer = instance.customer or (instance.sale.customer if instance.sale else None)
    if customer:
        customer.recalculate_balance()
