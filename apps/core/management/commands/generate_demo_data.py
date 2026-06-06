import random
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models, transaction
from django.contrib.auth.models import User

from apps.inventory.models import Product, Category, Brand, Batch, Purchase, PurchaseItem, StockOut, StockOutItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse, StockTransfer, StockTransferItem
from apps.core.models import AuditLog


class Command(BaseCommand):
    help = 'Generates 1 year of highly realistic demo data for testing reports, pagination, and dashboards.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Clearing existing transaction data..."))
        
        with transaction.atomic():
            # Delete transaction tables
            StockTransferItem.objects.all().delete()
            StockTransfer.objects.all().delete()
            StockOutItem.objects.all().delete()
            StockOut.objects.all().delete()
            SaleReturnItem.objects.all().delete()
            SaleReturn.objects.all().delete()
            SaleItem.objects.all().delete()
            Payment.objects.all().delete()
            Sale.objects.all().delete()
            PurchaseItem.objects.all().delete()
            Purchase.objects.all().delete()
            Batch.objects.all().delete()
            Product.objects.all().delete()
            Brand.objects.all().delete()
            Category.objects.all().delete()
            Customer.objects.all().delete()
            Warehouse.objects.all().delete()
            AuditLog.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Database cleared! Creating base metadata..."))

        # Get or create superuser for assignment
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write("Created default superuser 'admin' with password 'admin123'.")

        # 1. Create Categories
        categories_data = [
            ("Wall Clocks", "Decorative clocks designed for mounting on walls."),
            ("Wrist Watches", "Timepieces worn on the wrist."),
            ("Alarm Clocks", "Small table clocks designed to wake people up."),
            ("Smart Watches", "Wearable computers in the form of wristwatches."),
            ("Desk Clocks", "Elegant decorative clocks for desks and study tables.")
        ]
        categories = {}
        for name, desc in categories_data:
            cat = Category.objects.create(name=name, description=desc)
            categories[name] = cat

        # 2. Create Brands
        brands_data = [
            ("Seiko", "Renowned Japanese clock and watchmaker."),
            ("Casio", "Famous Japanese manufacturer of watches and electronics."),
            ("Citizen", "Japanese watchmaking brand known for Eco-Drive technology."),
            ("Garmin", "Leader in GPS navigation and sports smartwatch tech."),
            ("Fitbit", "American consumer electronics and fitness tracking company."),
            ("Rolex", "Swiss luxury watch manufacturer.")
        ]
        brands = {}
        for name, desc in brands_data:
            br = Brand.objects.create(name=name, description=desc)
            brands[name] = br

        # 3. Create Warehouses
        warehouses = {
            "Main Warehouse": Warehouse.objects.create(name="Main Warehouse", code="MWH", address="Plot 45, Industrial Zone", phone="01711122233", is_shop=False),
            "City Outlet Shop": Warehouse.objects.create(name="City Outlet Shop", code="COS", address="Level 2, City Center Mall", phone="01711122244", is_shop=True),
            "Dhanmondi Shop": Warehouse.objects.create(name="Dhanmondi Shop", code="DHS", address="Road 27, Dhanmondi", phone="01711122255", is_shop=True)
        }

        # 4. Create Customers
        customers_data = [
            ("Rahim Uddin", "01819234567", "rahim@example.com", "Dhanmondi, Dhaka"),
            ("Karim Khan", "01712345678", "karim@example.com", "Banani, Dhaka"),
            ("Anika Kabir", "01512345678", "anika@example.com", "Gulshan, Dhaka"),
            ("Zeeshan Alam", "01912345678", "zeeshan@example.com", "Uttara, Dhaka"),
            ("Nabila Chowdhury", "01612345678", "nabila@example.com", "Mirpur, Dhaka"),
            ("Sajid Hasan", "01312345678", "sajid@example.com", "Mohammadpur, Dhaka"),
            ("Farhana Islam", "01412345678", "farhana@example.com", "Wari, Dhaka"),
            ("Taskin Ahmed", "01722345678", "taskin@example.com", "Badda, Dhaka"),
            ("Ayesha Siddiqua", "01832345678", "ayesha@example.com", "Khilgaon, Dhaka")
        ]
        customers = []
        for name, phone, email, address in customers_data:
            cust = Customer.objects.create(name=name, phone=phone, email=email, address=address, credit_limit=Decimal('50000.00'))
            customers.append(cust)

        # 5. Create Products
        products_data = [
            ("Seiko 5 Sports", "Wrist Watches", "Seiko", "150.00", "SKU-SEI-5SP"),
            ("Casio G-Shock", "Wrist Watches", "Casio", "120.00", "SKU-CAS-GSH"),
            ("Citizen Eco-Drive", "Wrist Watches", "Citizen", "200.00", "SKU-CIT-ECO"),
            ("Garmin Fenix 7", "Smart Watches", "Garmin", "600.00", "SKU-GAR-FEN7"),
            ("Fitbit Charge 5", "Smart Watches", "Fitbit", "150.00", "SKU-FIT-CHG5"),
            ("Rolex Submariner", "Wrist Watches", "Rolex", "9500.00", "SKU-ROL-SUB"),
            ("Seiko Wall Clock QXH072B", "Wall Clocks", "Seiko", "80.00", "SKU-SEI-WC1"),
            ("Casio Alarm Clock PQ-30", "Alarm Clocks", "Casio", "15.00", "SKU-CAS-AC1"),
            ("Seiko Desk Clock QXQ037B", "Desk Clocks", "Seiko", "50.00", "SKU-SEI-DC1"),
            ("Citizen Wall Clock", "Wall Clocks", "Citizen", "75.00", "SKU-CIT-WC1")
        ]
        products = []
        for sku_name, cat_name, brand_name, price, sku in products_data:
            prod = Product.objects.create(
                sku=sku,
                category=categories[cat_name],
                brand=brands[brand_name],
                default_selling_price=Decimal(price),
                description=f"High quality clock/watch model: {sku_name}.",
                is_active=True
            )
            products.append(prod)

        self.stdout.write(self.style.SUCCESS("Metadata setup complete! Generating 1 year of timeline transactions..."))

        # Time range definition
        end_date = timezone.now().date()
        start_date = end_date - datetime.timedelta(days=365)
        
        current_date = start_date
        invoice_seq = 1
        po_seq = 1
        trf_seq = 1
        out_seq = 1
        batch_seq = 1

        # Keep track of active batches in the system
        # (batch_id -> Batch object) to avoid loading database in loops too much
        # We also need a helper to ensure we can stock-in products on demand if stock is low.
        
        def run_purchase(target_date, products_list):
            nonlocal po_seq, batch_seq
            po_num = f"PO{target_date.strftime('%Y%m%d')}{po_seq:04d}"
            po_seq += 1
            
            po = Purchase.objects.create(
                purchase_number=po_num,
                supplier=random.choice(["Global Time Distributors", "Classic Watch Suppliers Co.", "Premium Horology Ltd."]),
                purchase_date=target_date,
                total_amount=Decimal('0.00'),
                created_by=user
            )
            Purchase.objects.filter(pk=po.pk).update(created_at=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(9, 0))))
            
            total_amount = Decimal('0.00')
            for prod, quantity, unit_cost in products_list:
                batch_num = f"B{target_date.strftime('%Y%m%d')}{batch_seq:04d}"
                batch_seq += 1
                
                batch = Batch.objects.create(
                    batch_number=batch_num,
                    product=prod,
                    warehouse=warehouses["Main Warehouse"],
                    buy_price=unit_cost,
                    initial_quantity=quantity,
                    quantity=quantity,
                    purchase_date=target_date,
                    supplier=po.supplier,
                    notes=f"Initial stock-in via {po_num}"
                )
                Batch.objects.filter(pk=batch.pk).update(created_at=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(9, 5))))
                
                PurchaseItem.objects.create(
                    purchase=po,
                    batch=batch,
                    product=prod,
                    quantity=quantity,
                    unit_price=unit_cost
                )
                total_amount += quantity * unit_cost
                prod.update_total_stock()
                
            po.total_amount = total_amount
            po.save()

        def run_transfer(target_date, shop, items_list):
            nonlocal trf_seq
            trf_num = f"TRF{target_date.strftime('%Y%m%d')}{trf_seq:04d}"
            trf_seq += 1
            
            trf = StockTransfer.objects.create(
                transfer_number=trf_num,
                source_warehouse=warehouses["Main Warehouse"],
                destination_warehouse=shop,
                status='completed',
                transfer_date=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(10, 0))),
                completed_date=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(11, 0))),
                notes=f"Replenishment transfer to {shop.name}",
                created_by=user
            )
            StockTransfer.objects.filter(pk=trf.pk).update(created_at=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(10, 0))))
            
            for src_batch, qty in items_list:
                # Deduct from source batch
                src_batch.quantity -= qty
                src_batch.save()
                
                # Check for existing matching batch in shop
                dest_batch = Batch.objects.filter(
                    product=src_batch.product,
                    warehouse=shop,
                    buy_price=src_batch.buy_price
                ).first()
                
                if dest_batch:
                    dest_batch.quantity += qty
                    dest_batch.save()
                else:
                    nonlocal batch_seq
                    batch_num = f"B{target_date.strftime('%Y%m%d')}{batch_seq:04d}"
                    batch_seq += 1
                    dest_batch = Batch.objects.create(
                        product=src_batch.product,
                        warehouse=shop,
                        batch_number=batch_num,
                        buy_price=src_batch.buy_price,
                        purchase_date=src_batch.purchase_date,
                        initial_quantity=qty,
                        quantity=qty,
                        supplier=src_batch.supplier,
                        notes=f"Transferred from Main Warehouse via {trf_num}"
                    )
                    Batch.objects.filter(pk=dest_batch.pk).update(created_at=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(10, 30))))
                
                StockTransferItem.objects.create(
                    transfer=trf,
                    source_batch=src_batch,
                    destination_batch=dest_batch,
                    quantity=qty
                )
                src_batch.product.update_total_stock()

        def ensure_stock_in_shop(target_date, shop, product, quantity):
            """Helper to ensure a shop has stock to sell. Will stock in directly if needed."""
            # Find available batches of product in shop
            batches = Batch.objects.filter(product=product, warehouse=shop, quantity__gt=0)
            avail = sum(b.quantity for b in batches)
            
            if avail >= quantity:
                return
            
            # If not enough, see if we have stock in Main Warehouse
            needed = quantity - avail
            mwh_batches = Batch.objects.filter(product=product, warehouse=warehouses["Main Warehouse"], quantity__gt=0)
            mwh_avail = sum(b.quantity for b in mwh_batches)
            
            if mwh_avail < needed:
                # Purchase stock to Main Warehouse first
                buy_price = product.default_selling_price * Decimal(random.uniform(0.5, 0.7))
                run_purchase(target_date, [(product, needed + 50, buy_price)])
                mwh_batches = Batch.objects.filter(product=product, warehouse=warehouses["Main Warehouse"], quantity__gt=0)
            
            # Transfer from Main Warehouse to shop
            transfer_items = []
            accumulated = 0
            for b in mwh_batches:
                take = min(b.quantity, needed - accumulated)
                transfer_items.append((b, take))
                accumulated += take
                if accumulated >= needed:
                    break
            
            run_transfer(target_date, shop, transfer_items)

        # Pre-populate initial stock in Main Warehouse on day 1
        initial_purchases = []
        for prod in products:
            qty = random.randint(100, 200)
            cost = prod.default_selling_price * Decimal(random.uniform(0.5, 0.7))
            initial_purchases.append((prod, qty, cost))
        run_purchase(start_date, initial_purchases)

        # Distribute initial stock to both shops on day 1
        for shop in [warehouses["City Outlet Shop"], warehouses["Dhanmondi Shop"]]:
            initial_transfers = []
            for prod in products:
                b = Batch.objects.filter(product=prod, warehouse=warehouses["Main Warehouse"], quantity__gt=0).first()
                if b:
                    initial_transfers.append((b, random.randint(30, 50)))
            run_transfer(start_date, shop, initial_transfers)

        # Loop through each day of the year
        days_total = 365
        for i in range(days_total):
            current_date = start_date + datetime.timedelta(days=i)
            
            # 1. Weekly replenishment (every 7 days)
            if i % 7 == 0 and i > 0:
                # Purchase some new stock into Main Warehouse
                purchases_list = []
                for prod in random.sample(products, k=random.randint(3, 6)):
                    qty = random.randint(50, 100)
                    cost = prod.default_selling_price * Decimal(random.uniform(0.55, 0.68))
                    purchases_list.append((prod, qty, cost))
                run_purchase(current_date, purchases_list)

                # Transfer to shops if their stock is low
                for shop in [warehouses["City Outlet Shop"], warehouses["Dhanmondi Shop"]]:
                    transfers_list = []
                    for prod in products:
                        shop_stock = Batch.objects.filter(product=prod, warehouse=shop, quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
                        if shop_stock < 10:
                            # Transfer 20-40 units
                            b = Batch.objects.filter(product=prod, warehouse=warehouses["Main Warehouse"], quantity__gt=0).first()
                            if b:
                                qty_to_move = min(b.quantity, random.randint(20, 40))
                                if qty_to_move > 0:
                                    transfers_list.append((b, qty_to_move))
                    if transfers_list:
                        run_transfer(current_date, shop, transfers_list)

            # 2. Monthly stock out (loss / damages)
            if i % 30 == 0 and i > 0:
                out_num = f"OUT{current_date.strftime('%Y%m%d')}{out_seq:04d}"
                out_seq += 1
                
                shop = random.choice(list(warehouses.values()))
                prod = random.choice(products)
                batch = Batch.objects.filter(product=prod, warehouse=shop, quantity__gt=0).first()
                
                if batch and batch.quantity > 2:
                    qty = random.randint(1, 2)
                    st_out = StockOut.objects.create(
                        stockout_number=out_num,
                        warehouse=shop,
                        reason=random.choice(['damage', 'loss', 'expired', 'internal', 'adjustment']),
                        status='completed',
                        stockout_date=timezone.make_aware(datetime.datetime.combine(current_date, datetime.time(17, 30))),
                        completed_date=timezone.make_aware(datetime.datetime.combine(current_date, datetime.time(17, 45))),
                        notes=f"Audited stock adjustment: {qty} items found unusable.",
                        total_value=qty * batch.buy_price,
                        created_by=user
                    )
                    StockOut.objects.filter(pk=st_out.pk).update(created_at=timezone.make_aware(datetime.datetime.combine(current_date, datetime.time(17, 30))))
                    
                    StockOutItem.objects.create(
                        stockout=st_out,
                        batch=batch,
                        quantity=qty,
                        cost_price=batch.buy_price
                    )
                    batch.quantity -= qty
                    batch.save()
                    prod.update_total_stock()

            # 3. Daily Sales Invoices
            # Determine number of sales based on day of week (weekend gets more)
            is_weekend = current_date.weekday() in [4, 5]  # Friday/Saturday in Bangladesh context or standard Sat/Sun
            sales_count = random.randint(2, 6) if is_weekend else random.randint(1, 4)
            
            for _ in range(sales_count):
                shop = random.choice([warehouses["City Outlet Shop"], warehouses["Dhanmondi Shop"]])
                customer = random.choice([None] + customers) # 25% chance Walk-in, 75% chance registered
                
                # Number of unique products in the invoice
                item_kinds_count = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
                
                sale_products = random.sample(products, k=item_kinds_count)
                
                # Pre-check and ensure stock exists in the shop for selected products
                items_to_sell = []
                for prod in sale_products:
                    qty = random.randint(1, 2)
                    ensure_stock_in_shop(current_date, shop, prod, qty)
                    items_to_sell.append((prod, qty))
                
                # Now create the Sale Invoice
                inv_num = f"INV{current_date.strftime('%Y%m%d')}{invoice_seq:04d}"
                invoice_seq += 1
                
                sale_time = timezone.make_aware(datetime.datetime.combine(current_date, datetime.time(random.randint(10, 20), random.randint(0, 59))))
                
                sale = Sale.objects.create(
                    invoice_number=inv_num,
                    customer=customer,
                    sale_date=sale_time,
                    status='completed',
                    payment_status='unpaid',
                    created_by=user
                )
                Sale.objects.filter(pk=sale.pk).update(created_at=sale_time)
                
                subtotal = Decimal('0.00')
                total_cost = Decimal('0.00')
                
                for prod, qty in items_to_sell:
                    # Select batches in shop
                    batches = Batch.objects.filter(product=prod, warehouse=shop, quantity__gt=0).order_by('purchase_date')
                    remaining_qty = qty
                    
                    for b in batches:
                        sell_qty = min(b.quantity, remaining_qty)
                        
                        SaleItem.objects.create(
                            sale=sale,
                            product=prod,
                            batch=b,
                            quantity=sell_qty,
                            unit_price=prod.default_selling_price,
                            cost_price=b.buy_price
                        )
                        
                        b.quantity -= sell_qty
                        b.save()
                        
                        subtotal += sell_qty * prod.default_selling_price
                        total_cost += sell_qty * b.buy_price
                        remaining_qty -= sell_qty
                        
                        if remaining_qty <= 0:
                            break
                            
                    prod.update_total_stock()
                
                discount = Decimal('0.00')
                # 15% chance of flat discount (e.g. 5, 10, 20 etc.)
                if random.random() < 0.15:
                    discount = Decimal(random.choice([5, 10, 15, 20, 50]))
                    if discount > subtotal:
                        discount = Decimal('0.00')
                
                total = subtotal - discount
                
                sale.subtotal = subtotal
                sale.total_cost = total_cost
                sale.discount_amount = discount
                sale.total_amount = total
                
                # Determine payment status
                pay_roll = random.random()
                if pay_roll < 0.70:
                    # Fully Paid
                    sale.paid_amount = total
                    sale.payment_status = 'paid'
                    pay = Payment.objects.create(
                        customer=customer if customer else Customer.objects.get_or_create(name="Walk-in Customer")[0],
                        sale=sale,
                        amount=total,
                        payment_method=random.choice(['cash', 'card', 'mobile_payment']),
                        received_by=user
                    )
                    Payment.objects.filter(pk=pay.pk).update(payment_date=sale_time, created_at=sale_time)
                elif pay_roll < 0.85 and customer:
                    # Partially Paid (only if registered customer, walk-ins pay full)
                    paid = Decimal(random.randint(int(total * 20 // 100), int(total * 80 // 100)))
                    sale.paid_amount = paid
                    sale.payment_status = 'partial'
                    pay = Payment.objects.create(
                        customer=customer,
                        sale=sale,
                        amount=paid,
                        payment_method=random.choice(['cash', 'mobile_payment']),
                        received_by=user
                    )
                    Payment.objects.filter(pk=pay.pk).update(payment_date=sale_time, created_at=sale_time)
                else:
                    # Unpaid (only for registered customer, walk-ins pay full)
                    if customer:
                        sale.paid_amount = Decimal('0.00')
                        sale.payment_status = 'unpaid'
                    else:
                        sale.paid_amount = total
                        sale.payment_status = 'paid'
                        pay = Payment.objects.create(
                            customer=Customer.objects.get_or_create(name="Walk-in Customer")[0],
                            sale=sale,
                            amount=total,
                            payment_method='cash',
                            received_by=user
                        )
                        Payment.objects.filter(pk=pay.pk).update(payment_date=sale_time, created_at=sale_time)
                
                sale.save()

            if (i+1) % 50 == 0:
                self.stdout.write(f"Processed {i+1} days of transactions...")

        self.stdout.write(self.style.WARNING("Recalculating all customer balances..."))
        # Recalculate customer statistics
        for cust in Customer.objects.all():
            cust.recalculate_balance()
            
        self.stdout.write(self.style.SUCCESS("Successfully generated 1 year of demo data!"))
