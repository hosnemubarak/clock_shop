import json
from decimal import Decimal
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse
from apps.inventory.models import Product, ProductStock

class SaleService:
    @staticmethod
    def create_from_pos(data, user):
        """
        Create a sale from POS checkout data.
        Resolves D-6, D-7, and D-8 by extracting logic from view,
        handling JSON safely, and prefetching related objects.
        """
        shop = Warehouse.objects.filter(is_shop=True).first()
        if not shop:
            raise ValueError('No shop warehouse configured.')
            
        items = data.get('items', [])
        if not items:
            raise ValueError('Cart is empty.')
            
        customer_id = data.get('customer_id')
        discount_amount = Decimal(str(data.get('discount_amount', '0') or '0'))
        payment_amount = Decimal(str(data.get('payment_amount', '0') or '0'))
        payment_method = data.get('payment_method', 'cash')
        
        customer = None
        if customer_id:
            customer = Customer.objects.filter(pk=customer_id).first()
            
        # Parse date
        sale_date_str = data.get('sale_date')
        if sale_date_str:
            parsed = parse_datetime(sale_date_str) or parse_date(sale_date_str)
            if hasattr(parsed, 'date'):
                sale_date = parsed.date()
            else:
                sale_date = parsed if parsed else timezone.now().date()
        else:
            sale_date = timezone.now().date()
            
        sale = Sale.objects.create(
            customer=customer,
            sale_date=sale_date,
            discount_amount=discount_amount,
            notes=data.get('notes', ''),
            created_by=user,
            status='completed' if payment_amount > 0 else 'pending'
        )
        
        subtotal = Decimal('0')
        total_cost = Decimal('0')
        
        # Prefetch to avoid N+1 queries in loop
        product_ids = [item['product_id'] for item in items]
        products_map = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
        stocks_map = {
            s.product_id: s 
            for s in ProductStock.objects.select_for_update().filter(
                product_id__in=product_ids, warehouse=shop
            )
        }
        
        sale_items_to_create = []
        stocks_to_update = []
        
        for item_data in items:
            product = products_map.get(int(item_data['product_id']))
            if not product:
                raise ValueError(f"Product with ID {item_data['product_id']} not found.")
                
            quantity = int(item_data['quantity'])
            unit_price = Decimal(str(item_data['unit_price']))
            
            # Stock check
            stock = stocks_map.get(product.id)
            if not stock or quantity > stock.quantity:
                raise ValueError(f'Insufficient stock for {product.display_name}')
                
            sale_items_to_create.append(SaleItem(
                sale=sale,
                product=product,
                warehouse=shop,
                quantity=quantity,
                unit_price=unit_price,
                cost_price=product.average_cost,
                discount=Decimal('0')
            ))
            
            # Update Stock
            stock.quantity -= quantity
            stocks_to_update.append(stock)
            
        # Bulk create items and update stock
        SaleItem.objects.bulk_create(sale_items_to_create)
        ProductStock.objects.bulk_update(stocks_to_update, ['quantity'])
        
        for stock in stocks_to_update:
            stock.product.update_total_stock()
            
        for si in sale_items_to_create:
            subtotal += si.quantity * si.unit_price
            total_cost += si.quantity * si.cost_price
            
        # Finalize Sale Totals
        sale.subtotal = subtotal
        sale.total_cost = total_cost
        sale.total_amount = subtotal - discount_amount
        
        # Determine status based on payment
        if payment_amount >= sale.total_amount:
            sale.status = 'paid'
        elif payment_amount > 0:
            sale.status = 'partial'
            
        sale.save()
        
        # Create Payment
        if payment_amount > 0:
            Payment.objects.create(
                customer=customer,
                sale=sale,
                amount=payment_amount,
                payment_date=timezone.now(),
                payment_method=payment_method,
                reference=f'POS-{sale.invoice_number}',
                received_by=user,
                notes='POS Checkout Payment'
            )
            # Signal will handle customer balance update
        else:
            # If no payment but customer exists, we must recalculate balance (new sale)
            if customer:
                customer.recalculate_balance()
                
        return sale, payment_amount
