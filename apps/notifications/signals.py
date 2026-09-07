import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.sales.models import Sale
from apps.customers.models import Payment

from django.db import transaction

logger = logging.getLogger(__name__)

CURRENCY = getattr(settings, 'CURRENCY_SYMBOL', '৳')


def format_sale_message(sale):
    """Format a detailed, meaningful sale notification from database attributes."""
    if sale.customer:
        phone_part = f" ({sale.customer.phone})" if sale.customer.phone else ""
        customer_name = f"{sale.customer.name}{phone_part}"
        customer_total_due = f"{CURRENCY}{sale.customer.total_due:,.2f}"
    else:
        customer_name = "Walk-in Customer"
        customer_total_due = None

    status_map = {
        'paid': '🟢 Fully Paid',
        'partial': '🟡 Partially Paid',
        'unpaid': '🔴 Unpaid',
    }
    status_label = status_map.get(sale.payment_status, sale.get_payment_status_display())

    total_str = f"{CURRENCY}{sale.total_amount:,.2f}"
    paid_str = f"{CURRENCY}{sale.paid_amount:,.2f}"
    due_str = f"{CURRENCY}{sale.due_amount:,.2f}"

    lines = [
        "🧾 New Sale Created",
        "",
        f"Invoice: #{sale.invoice_number}",
        f"Customer: {customer_name}",
        f"Payment Status: {status_label}",
        f"Total Amount: {total_str}",
        f"Paid Amount: {paid_str}",
        f"Due Amount: {due_str}",
    ]

    if customer_total_due:
        lines.append(f"Customer Total Due: {customer_total_due}")

    if sale.discount_amount and sale.discount_amount > 0:
        lines.append(f"Discount: {CURRENCY}{sale.discount_amount:,.2f}")

    # Line items summary
    items = list(sale.items.select_related('product')[:5])
    total_item_count = sale.items.count()
    if items:
        lines.append("")
        lines.append(f"Items ({total_item_count}):")
        for item in items:
            name = item.product.display_name if item.product else (item.custom_description or "Item")
            lines.append(f"• {name} (x{item.quantity})")
        if total_item_count > 5:
            lines.append(f"• ... and {total_item_count - 5} more items")

    served_by = sale.created_by.username if sale.created_by else 'System'
    date_str = (sale.created_at or sale.sale_date).strftime('%Y-%m-%d %H:%M') if hasattr(sale, 'created_at') and sale.created_at else str(sale.sale_date)

    lines.append("")
    lines.append(f"Served By: {served_by}")
    lines.append(f"Date: {date_str}")

    return "\n".join(lines)


def format_payment_message(payment):
    """Format a detailed, meaningful payment notification from database attributes."""
    customer = payment.customer or (payment.sale.customer if payment.sale else None)
    if customer:
        phone_part = f" ({customer.phone})" if customer.phone else ""
        customer_name = f"{customer.name}{phone_part}"
        customer_total_due = f"{CURRENCY}{customer.total_due:,.2f}"
    else:
        customer_name = "Walk-in Customer"
        customer_total_due = None

    method_display = payment.get_payment_method_display()
    if payment.reference:
        method_display += f" (Ref: {payment.reference})"

    lines = [
        "💳 Payment Received",
        "",
        f"Amount Paid: {CURRENCY}{payment.amount:,.2f}",
        f"Payment Method: {method_display}",
        f"Customer: {customer_name}",
    ]

    if payment.sale:
        sale = payment.sale
        status_map = {
            'paid': '🟢 Fully Paid',
            'partial': '🟡 Partially Paid',
            'unpaid': '🔴 Unpaid',
        }
        sale_status = status_map.get(sale.payment_status, sale.get_payment_status_display())
        lines.append(f"Invoice: #{sale.invoice_number}")
        lines.append(f"Invoice Total: {CURRENCY}{sale.total_amount:,.2f}")
        lines.append(f"Invoice Due: {CURRENCY}{sale.due_amount:,.2f} ({sale_status})")

    if customer_total_due:
        lines.append(f"Customer Total Due: {customer_total_due}")

    received_by = payment.received_by.username if payment.received_by else 'System'
    date_str = payment.payment_date.strftime('%Y-%m-%d %H:%M') if payment.payment_date else ""

    lines.append("")
    lines.append(f"Received By: {received_by}")
    if date_str:
        lines.append(f"Date: {date_str}")

    return "\n".join(lines)


@receiver(post_save, sender=Sale)
def on_sale_created(sender, instance, created, **kwargs):
    """Send a Telegram notification when a new completed sale is created."""
    if not created:
        return
    if instance.status != Sale.Status.COMPLETED:
        return

    sale_id = instance.pk

    def _send():
        try:
            sale = (
                Sale.objects
                .select_related('customer', 'created_by')
                .prefetch_related('items__product')
                .filter(pk=sale_id)
                .first()
            )
            if not sale:
                return

            message = format_sale_message(sale)
            from .services import notify
            notify(
                event_type='sale_created',
                event_id=sale.pk,
                message=message,
            )
        except Exception:
            logger.exception('Notification failed for sale %s (non-blocking)', sale_id)

    transaction.on_commit(_send)


@receiver(post_save, sender=Payment)
def on_payment_received(sender, instance, created, **kwargs):
    """Send a Telegram notification when a new payment is recorded."""
    if not created:
        return

    payment_id = instance.pk

    def _send():
        try:
            payment = (
                Payment.objects
                .select_related('customer', 'sale', 'sale__customer', 'received_by')
                .filter(pk=payment_id)
                .first()
            )
            if not payment:
                return

            message = format_payment_message(payment)
            from .services import notify
            notify(
                event_type='payment_received',
                event_id=payment.pk,
                message=message,
            )
        except Exception:
            logger.exception('Notification failed for payment %s (non-blocking)', payment_id)

    transaction.on_commit(_send)
