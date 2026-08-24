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
        shop = Warehouse.objects.filter(is_shop=True, is_active=True).first()
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
            is_custom = item_data.get('is_custom') is True
            if not is_custom and item_data.get('product_id') in (None, ''):
                raise ValueError(f'Cart item #{index} is missing a product.')
            if not is_custom and item_data.get('unit_price') in (None, ''):
                raise ValueError(f'Cart item #{index} is missing a unit price.')

            description = str(item_data.get('custom_description') or '').strip()
            if is_custom and not description:
                raise ValueError(f'Custom description for item #{index} is required.')
            if is_custom and len(description) > 255:
                raise ValueError(f'Custom description for item #{index} cannot exceed 255 characters.')

            quantity = _to_int(
                item_data.get('quantity', 1) if is_custom else item_data.get('quantity'),
                f'quantity for item #{index}'
            )
            if quantity <= 0:
                raise ValueError(f'Quantity for item #{index} must be greater than zero.')

            unit_price = _to_decimal(
                item_data.get('unit_price', 0) if is_custom else item_data.get('unit_price'),
                f'unit price for item #{index}'
            )
            if unit_price < 0:
                raise ValueError(f'Unit price for item #{index} cannot be negative.')

            # Per-line discount is an absolute amount off that line, mirroring
            # SaleItem.total_price = quantity * unit_price - discount. Absent or
            # blank means no discount, so an older client keeps working unchanged.
            discount = _to_decimal(item_data.get('discount'), f'discount for item #{index}')
            if discount < 0:
                raise ValueError(f'Discount for item #{index} cannot be negative.')
            if discount > quantity * unit_price:
                raise ValueError(f'Discount for item #{index} cannot exceed the line total.')

            parsed_items.append({
                'product_id': None if is_custom else _to_int(
                    item_data.get('product_id'), f'product for item #{index}'
                ),
                'quantity': quantity,
                'unit_price': unit_price,
                'discount': discount,
                'is_custom': is_custom,
                'custom_description': description,
            })

        customer_id = data.get('customer_id')
        discount_amount = _to_decimal(data.get('discount_amount'), 'discount amount')
        payment_amount = _to_decimal(data.get('payment_amount'), 'payment amount')
        payment_method = data.get('payment_method', 'cash')

        # The model validators do not fire on Model.objects.create(), so a negative
        # order discount would inflate total_amount and a negative payment would
        # corrupt the customer balance. Reject all three here.
        if discount_amount < 0:
            raise ValueError('Order discount cannot be negative.')
        if payment_amount < 0:
            raise ValueError('Payment amount cannot be negative.')

        # choices are not enforced at the database level either, so an unknown
        # method used to persist and then render blank on the payment reports.
        if payment_method not in Payment.PaymentMethod.values:
            raise ValueError(f'Unknown payment method: {payment_method!r}')
        
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
        product_ids = sorted({item['product_id'] for item in parsed_items if not item['is_custom']})
        products_map = {
            p.id: p for p in Product.objects.filter(id__in=product_ids, is_active=True)
        }
        stocks_map = {
            s.product_id: s
            for s in ProductStock.objects.select_for_update().filter(
                product_id__in=product_ids, warehouse=shop
            ).order_by('product_id')
        }

        sale_items_to_create = []
        stocks_to_update = []

        for item_data in parsed_items:
            if item_data['is_custom']:
                sale_items_to_create.append(SaleItem(
                    sale=sale,
                    product=None,
                    warehouse=None,
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    cost_price=Decimal('0.00'),
                    discount=item_data['discount'],
                    is_custom=True,
                    custom_description=item_data['custom_description'],
                ))
                continue

            product = products_map.get(item_data['product_id'])
            if not product:
                raise ValueError(
                    f"Product with ID {item_data['product_id']} not found or inactive."
                )

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
                discount=item_data['discount']
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
            # total_price nets the per-line discount, matching Sale.calculate_totals().
            # Multiplying out by hand here would over-charge every discounted line and
            # let a later calculate_totals() silently rewrite the invoice.
            subtotal += si.total_price
            total_cost += si.total_cost
            
        # Finalize Sale Totals
        if discount_amount > subtotal:
            raise ValueError('Order discount cannot exceed the sale subtotal.')

        total_amount = subtotal - discount_amount
        if payment_amount > total_amount:
            payment_amount = total_amount

        due_amount = total_amount - payment_amount
        if due_amount > 0:
            if not customer:
                raise ValueError('Walk-in customers cannot have unpaid balances. Full payment required.')
            if customer.credit_limit > 0 and (customer.total_due + due_amount > customer.credit_limit):
                raise ValueError(f"Credit limit exceeded! Customer's limit is {customer.credit_limit} Tk (currently owes {customer.total_due} Tk).")

        sale.subtotal = subtotal
        sale.total_cost = total_cost
        sale.total_amount = subtotal - discount_amount
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
