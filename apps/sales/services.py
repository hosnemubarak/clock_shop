from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse
from apps.inventory.models import Product, ProductStock


def _to_decimal(value, label):
    """Coerce a payload value to Decimal, raising ValueError (not ArithmeticError)."""
    try:
        return Decimal(str(value if value not in (None, '') else '0'))
    except (InvalidOperation, TypeError):
        raise ValueError(f'Invalid {label}: {value!r}')


def _to_int(value, label):
    """Coerce a payload value to int, raising ValueError on anything unusable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid {label}: {value!r}')


class SaleService:
    @staticmethod
    @transaction.atomic
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

        # Coerce the whole cart before any write: a bad payload would otherwise raise
        # KeyError / InvalidOperation and escape as HTTP 500 instead of a 400.
        parsed_items = []
        for index, item_data in enumerate(items, start=1):
            if not isinstance(item_data, dict):
                raise ValueError(f'Invalid cart item #{index}: {item_data!r}')
            if item_data.get('product_id') in (None, ''):
                raise ValueError(f'Cart item #{index} is missing a product.')
            if item_data.get('unit_price') in (None, ''):
                raise ValueError(f'Cart item #{index} is missing a unit price.')

            quantity = _to_int(item_data.get('quantity'), f'quantity for item #{index}')
            if quantity <= 0:
                raise ValueError(f'Quantity for item #{index} must be greater than zero.')

            unit_price = _to_decimal(item_data.get('unit_price'), f'unit price for item #{index}')
            if unit_price < 0:
                raise ValueError(f'Unit price for item #{index} cannot be negative.')

            parsed_items.append({
                'product_id': _to_int(item_data.get('product_id'), f'product for item #{index}'),
                'quantity': quantity,
                'unit_price': unit_price,
            })

        customer_id = data.get('customer_id')
        discount_amount = _to_decimal(data.get('discount_amount'), 'discount amount')
        payment_amount = _to_decimal(data.get('payment_amount'), 'payment amount')
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
                sale_date = parsed if parsed else timezone.localdate()
        else:
            sale_date = timezone.localdate()
            
        sale = Sale.objects.create(
            customer=customer,
            sale_date=sale_date,
            discount_amount=discount_amount,
            notes=data.get('notes', ''),
            created_by=user,
            status=Sale.Status.COMPLETED
        )
        
        subtotal = Decimal('0')
        total_cost = Decimal('0')
        
        # Prefetch to avoid N+1 queries in loop. Lock the stock rows in a stable
        # order so two concurrent checkouts cannot deadlock against each other.
        product_ids = sorted({item['product_id'] for item in parsed_items})
        products_map = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
        stocks_map = {
            s.product_id: s
            for s in ProductStock.objects.select_for_update().filter(
                product_id__in=product_ids, warehouse=shop
            ).order_by('product_id')
        }

        sale_items_to_create = []
        stocks_to_update = []

        for item_data in parsed_items:
            product = products_map.get(item_data['product_id'])
            if not product:
                raise ValueError(f"Product with ID {item_data['product_id']} not found.")

            quantity = item_data['quantity']
            unit_price = item_data['unit_price']
            
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
        
        # Use the already-fetched Product objects: stock.product would lazy-load
        # one extra query per line item. select_related() is not an option here
        # because it would make select_for_update() lock the product rows too.
        for stock in stocks_to_update:
            products_map[stock.product_id].update_total_stock()

        for si in sale_items_to_create:
            subtotal += si.quantity * si.unit_price
            total_cost += si.quantity * si.cost_price
            
        # Finalize Sale Totals
        sale.subtotal = subtotal
        sale.total_cost = total_cost
        sale.total_amount = subtotal - discount_amount + sale.tax_amount
        sale.save(update_fields=['subtotal', 'total_cost', 'total_amount'])

        # Create Payment
        if payment_amount > 0:
            Payment.objects.create(
                customer=customer,
                sale=sale,
                amount=payment_amount,
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
