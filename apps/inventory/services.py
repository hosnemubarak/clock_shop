from decimal import Decimal
from django.db import transaction
from django.utils import timezone


def get_product_stock_history(product, limit=None):
    """
    Retrieves chronological stock history for a product from all transactional tables:
    PurchaseItem, SaleItem, SaleReturnItem, StockOutItem, StockTransferItem.
    """
    history = []
    
    # 1. Purchases (Stock In)
    for pi in product.purchaseitem_set.select_related('purchase', 'purchase__created_by', 'warehouse'):
        history.append({
            'timestamp': pi.created_at,
            'date': pi.purchase.purchase_date,
            'type': 'STOCK_IN',
            'type_label': 'Stock In (Purchase)',
            'reference': pi.purchase.purchase_number,
            'warehouse': pi.warehouse.name if pi.warehouse else 'N/A',
            'quantity': pi.quantity,
            'price': pi.unit_price,
            'user': pi.purchase.created_by.get_full_name() if pi.purchase.created_by else 'System',
            'is_positive': True,
            'purchase_id': pi.purchase_id,
            'item_id': pi.id,
        })
        
    # 2. Sales (Stock Out)
    from apps.sales.models import SaleItem, SaleReturnItem
    
    sale_items = SaleItem.objects.filter(product=product).exclude(sale__status='cancelled').select_related('sale', 'sale__created_by', 'warehouse')
    for si in sale_items:
        history.append({
            'timestamp': si.created_at,
            'date': si.sale.sale_date,
            'type': 'SALE',
            'type_label': 'Sale',
            'reference': si.sale.invoice_number,
            'warehouse': si.warehouse.name if si.warehouse else 'N/A',
            'quantity': -si.quantity,
            'price': si.unit_price,
            'user': si.sale.created_by.get_full_name() if si.sale.created_by else 'System',
            'is_positive': False,
            'sale_id': si.sale_id,
            'item_id': si.id,
        })
        
    # 3. Sale Returns (Stock In)
    return_items = SaleReturnItem.objects.filter(sale_item__product=product).select_related('sale_return', 'sale_return__created_by', 'sale_item__warehouse')
    for ri in return_items:
        history.append({
            'timestamp': ri.created_at,
            'date': ri.sale_return.return_date,
            'type': 'RETURN',
            'type_label': 'Sale Return',
            'reference': ri.sale_return.return_number,
            'warehouse': ri.sale_item.warehouse.name if ri.sale_item.warehouse else 'N/A',
            'quantity': ri.quantity,
            'price': ri.sale_item.unit_price,
            'user': ri.sale_return.created_by.get_full_name() if ri.sale_return.created_by else 'System',
            'is_positive': True,
            'return_id': ri.sale_return_id,
            'item_id': ri.id,
        })
        
    # 4. Stock Out (Damaged / Lost)
    for so in product.stockout_items.exclude(stockout__status='cancelled').select_related('stockout', 'stockout__created_by', 'stockout__warehouse'):
        history.append({
            'timestamp': so.created_at,
            'date': so.stockout.stockout_date,
            'type': 'STOCK_OUT',
            'type_label': f'Stock Out ({so.stockout.get_reason_display()})',
            'reference': so.stockout.stockout_number,
            'warehouse': so.stockout.warehouse.name if so.stockout.warehouse else 'N/A',
            'quantity': -so.quantity,
            'price': so.cost_price,
            'user': so.stockout.created_by.get_full_name() if so.stockout.created_by else 'System',
            'is_positive': False,
            'stockout_id': so.stockout_id,
            'item_id': so.id,
        })
        
    # 5. Transfers
    for ti in product.transfer_items.exclude(transfer__status='cancelled').select_related('transfer', 'transfer__created_by', 'transfer__source_warehouse', 'transfer__destination_warehouse'):
        history.append({
            'timestamp': ti.created_at,
            'date': ti.transfer.transfer_date,
            'type': 'TRANSFER',
            'type_label': 'Transfer',
            'reference': ti.transfer.transfer_number,
            'warehouse': f"{ti.transfer.source_warehouse.name} ➔ {ti.transfer.destination_warehouse.name}",
            'quantity': ti.quantity,
            'price': 0,
            'user': ti.transfer.created_by.get_full_name() if ti.transfer.created_by else 'System',
            'is_positive': None,
            'transfer_id': ti.transfer_id,
            'item_id': ti.id,
        })
        
    # Sort history by timestamp descending (newest first)
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if limit:
        return history[:limit]
        
    return history


def recalculate_product_costing(product):
    """
    Recalculate perpetual moving weighted average cost for a product from its
    entire transaction history and synchronize cost prices for historical
    SaleItem and StockOutItem records.

    Rules & Invariants:
    - Quantities in warehouses (ProductStock) are never modified.
    - Customer sale amounts, invoices, and customer dues are never modified.
    - Only cost prices, total costs, and product average_cost are updated.
    """
    from apps.sales.models import Sale, SaleItem, SaleReturnItem
    from apps.inventory.models import Product, PurchaseItem, StockOut, StockOutItem

    purchases = list(PurchaseItem.objects.filter(product=product).select_related('purchase'))
    sales = list(SaleItem.objects.filter(product=product).exclude(
        sale__status=Sale.Status.CANCELLED
    ).select_related('sale'))
    stockouts = list(StockOutItem.objects.filter(product=product).exclude(
        stockout__status=StockOut.Status.CANCELLED
    ).select_related('stockout'))
    returns = list(SaleReturnItem.objects.filter(
        sale_item__product=product
    ).select_related('sale_return', 'sale_item'))

    events = []

    for pi in purchases:
        events.append({
            'date': pi.purchase.purchase_date,
            'type_order': 0,  # Purchases first on a given date
            'created_at': pi.created_at,
            'id': pi.id,
            'event_type': 'PURCHASE',
            'item': pi,
        })

    for ri in returns:
        rdate = ri.sale_return.return_date
        events.append({
            'date': rdate.date() if hasattr(rdate, 'date') else rdate,
            'type_order': 1,  # Returns second
            'created_at': ri.created_at,
            'id': ri.id,
            'event_type': 'RETURN',
            'item': ri,
        })

    for so in stockouts:
        sdate = so.stockout.stockout_date
        events.append({
            'date': sdate.date() if hasattr(sdate, 'date') else sdate,
            'type_order': 2,  # Stockouts third
            'created_at': so.created_at,
            'id': so.id,
            'event_type': 'STOCK_OUT',
            'item': so,
        })

    for si in sales:
        events.append({
            'date': si.sale.sale_date,
            'type_order': 3,  # Sales fourth
            'created_at': si.created_at,
            'id': si.id,
            'event_type': 'SALE',
            'item': si,
        })

    events.sort(key=lambda e: (e['date'], e['type_order'], e['created_at'], e['id']))

    running_stock = 0
    running_avg_cost = Decimal('0.00')
    affected_sales = set()
    affected_stockouts = set()

    for event in events:
        etype = event['event_type']
        if etype == 'PURCHASE':
            pi = event['item']
            qty = pi.quantity
            price = pi.unit_price
            if running_stock <= 0:
                running_avg_cost = price
                running_stock = qty
            else:
                total_val = (Decimal(running_stock) * running_avg_cost) + (Decimal(qty) * price)
                running_stock += qty
                running_avg_cost = total_val / Decimal(running_stock)

        elif etype == 'RETURN':
            ri = event['item']
            running_stock += ri.quantity

        elif etype == 'STOCK_OUT':
            so = event['item']
            target_cost = running_avg_cost.quantize(Decimal('0.01'))
            if so.cost_price != target_cost:
                so.cost_price = target_cost
                so.save(update_fields=['cost_price'])
                affected_stockouts.add(so.stockout_id)
            running_stock = max(0, running_stock - so.quantity)

        elif etype == 'SALE':
            si = event['item']
            target_cost = running_avg_cost.quantize(Decimal('0.01'))
            if si.cost_price != target_cost:
                si.cost_price = target_cost
                si.save(update_fields=['cost_price'])
                affected_sales.add(si.sale_id)
            net_qty = si.quantity - si.returned_quantity
            running_stock = max(0, running_stock - net_qty)

    product.average_cost = running_avg_cost.quantize(Decimal('0.01'))
    product.save(update_fields=['average_cost'])

    for sale_id in affected_sales:
        sale = Sale.objects.get(id=sale_id)
        sale.calculate_totals()

    for so_id in affected_stockouts:
        so = StockOut.objects.get(id=so_id)
        so.total_value = sum(item.quantity * item.cost_price for item in so.items.all())
        so.save(update_fields=['total_value'])

    return product.average_cost


@transaction.atomic
def update_purchase_item_cost(purchase_item, new_unit_price, user=None, reason='', request=None):
    """
    Updates the cost price (unit_price) of a PurchaseItem, recalculates the purchase total,
    recalculates the product's average cost and historical sales COGS, and records an AuditLog.
    """
    from apps.core.models import AuditLog
    from apps.core.utils import create_audit_log
    from apps.inventory.models import Product, PurchaseItem

    if new_unit_price < Decimal('0.00'):
        raise ValueError('Unit price cannot be negative.')

    pi = PurchaseItem.objects.select_for_update().select_related('purchase', 'product').get(pk=purchase_item.pk)
    old_unit_price = pi.unit_price
    purchase = pi.purchase
    old_purchase_total = purchase.total_amount
    product = Product.objects.select_for_update().get(pk=pi.product_id)
    old_avg_cost = product.average_cost

    pi.unit_price = new_unit_price
    pi.save(update_fields=['unit_price'])

    new_purchase_total = sum(item.total_price for item in purchase.items.all())
    purchase.total_amount = new_purchase_total
    purchase.save(update_fields=['total_amount'])

    new_avg_cost = recalculate_product_costing(product)

    changes = {
        'action': 'edit_cost_price',
        'purchase_number': purchase.purchase_number,
        'item_id': pi.id,
        'product_sku': product.sku,
        'old_unit_price': str(old_unit_price),
        'new_unit_price': str(new_unit_price),
        'old_purchase_total': str(old_purchase_total),
        'new_purchase_total': str(new_purchase_total),
        'old_average_cost': str(old_avg_cost),
        'new_average_cost': str(new_avg_cost),
        'reason': reason or 'Cost price correction',
    }
    if request:
        create_audit_log(request, AuditLog.Action.UPDATE, purchase, changes)
    else:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.UPDATE,
            model_name='Purchase',
            object_id=purchase.id,
            object_repr=str(purchase),
            changes=changes,
        )

    return {
        'item': pi,
        'purchase': purchase,
        'product': product,
        'old_unit_price': old_unit_price,
        'new_unit_price': new_unit_price,
        'old_avg_cost': old_avg_cost,
        'new_avg_cost': new_avg_cost,
    }


@transaction.atomic
def update_purchase_and_costs(purchase, purchase_data, item_prices, user=None, reason='', request=None):
    """
    Updates purchase header fields (supplier, purchase_date, notes) and unit prices
    for multiple items in a purchase, recalculates purchase total amount and product
    costing for all affected products.
    """
    from apps.core.models import AuditLog
    from apps.core.utils import create_audit_log
    from apps.inventory.models import Product, Purchase, PurchaseItem

    locked_purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    old_total = locked_purchase.total_amount

    # Update header fields if provided
    if 'supplier' in purchase_data:
        locked_purchase.supplier = purchase_data['supplier']
    if 'purchase_date' in purchase_data and purchase_data['purchase_date']:
        locked_purchase.purchase_date = purchase_data['purchase_date']
    if 'notes' in purchase_data:
        locked_purchase.notes = purchase_data['notes']

    affected_products = {}
    item_changes = []

    items = list(locked_purchase.items.select_for_update().select_related('product'))
    for item in items:
        if item.id in item_prices:
            new_price = item_prices[item.id]
            if new_price < Decimal('0.00'):
                raise ValueError(f'Unit price for {item.product.sku} cannot be negative.')
            if new_price != item.unit_price:
                old_price = item.unit_price
                item.unit_price = new_price
                item.save(update_fields=['unit_price'])
                affected_products[item.product_id] = item.product
                item_changes.append({
                    'item_id': item.id,
                    'sku': item.product.sku,
                    'old_price': str(old_price),
                    'new_price': str(new_price),
                })

    # Recalculate purchase total
    new_total = sum(i.total_price for i in locked_purchase.items.all())
    locked_purchase.total_amount = new_total
    locked_purchase.save(update_fields=['supplier', 'purchase_date', 'notes', 'total_amount'])

    # Recalculate costing for affected products
    for product_id, product in affected_products.items():
        locked_product = Product.objects.select_for_update().get(pk=product_id)
        recalculate_product_costing(locked_product)

    changes = {
        'action': 'edit_purchase_and_costs',
        'purchase_number': locked_purchase.purchase_number,
        'old_total': str(old_total),
        'new_total': str(new_total),
        'items_changed': item_changes,
        'reason': reason or 'Purchase and cost correction',
    }
    if request:
        create_audit_log(request, AuditLog.Action.UPDATE, locked_purchase, changes)
    else:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.UPDATE,
            model_name='Purchase',
            object_id=locked_purchase.id,
            object_repr=str(locked_purchase),
            changes=changes,
        )

    return locked_purchase
