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
            'is_positive': True
        })
        
    # 2. Sales (Stock Out)
    # We need to query SaleItem where product matches.
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
            'is_positive': False
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
            'price': ri.sale_item.unit_price,  # Approximate value
            'user': ri.sale_return.created_by.get_full_name() if ri.sale_return.created_by else 'System',
            'is_positive': True
        })
        
    # 4. Stock Out (Damaged / Lost)
    for so in product.stockout_items.exclude(stockout__status='cancelled').select_related('stockout', 'stockout__created_by', 'stockout__warehouse'):
        history.append({
            'timestamp': so.created_at,
            'date': so.stockout.date,
            'type': 'STOCK_OUT',
            'type_label': f'Stock Out ({so.stockout.get_reason_display()})',
            'reference': so.stockout.reference_number,
            'warehouse': so.stockout.warehouse.name if so.stockout.warehouse else 'N/A',
            'quantity': -so.quantity,
            'price': so.cost_price,
            'user': so.stockout.created_by.get_full_name() if so.stockout.created_by else 'System',
            'is_positive': False
        })
        
    # 5. Transfers
    for ti in product.transfer_items.exclude(transfer__status='cancelled').select_related('transfer', 'transfer__created_by', 'transfer__source_warehouse', 'transfer__destination_warehouse'):
        # For a transfer, from the product's perspective, it left source and entered destination.
        # We'll represent it as a single line item.
        history.append({
            'timestamp': ti.created_at,
            'date': ti.transfer.transfer_date,
            'type': 'TRANSFER',
            'type_label': 'Transfer',
            'reference': ti.transfer.reference_number,
            'warehouse': f"{ti.transfer.source_warehouse.name} ➔ {ti.transfer.destination_warehouse.name}",
            'quantity': ti.quantity,
            'price': 0,
            'user': ti.transfer.created_by.get_full_name() if ti.transfer.created_by else 'System',
            'is_positive': None  # Neutral since it's just moving
        })
        
    # Sort history by timestamp descending (newest first)
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if limit:
        return history[:limit]
        
    return history
