import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker

from apps.core.models import SystemSettings, AuditLog
from apps.customers.models import Customer, Payment, CustomerNote
from apps.inventory.models import Category, Brand, Product, Batch, Purchase, PurchaseItem, StockOut, StockOutItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from apps.warehouse.models import Warehouse, StockTransfer, StockTransferItem


class Command(BaseCommand):
    help = 'Generates 20 dummy records for each table'

    def handle(self, *args, **kwargs):
        fake = Faker('bn_BD')
        fake_en = Faker('en_US')
        
        self.stdout.write('Generating Dummy Data...')

        # SystemSettings
        settings = SystemSettings.get_settings()
        settings.shop_name = 'Dhaka Clock Traders'
        settings.currency_symbol = '৳'
        settings.save()
        self.stdout.write('Created SystemSettings.')

        # Users
        users = []
        for i in range(20):
            username = fake_en.user_name() + str(random.randint(100, 999))
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': fake_en.email()}
            )
            users.append(user)
        self.stdout.write('Created 20 Users.')

        # Warehouses
        cities = ['Dhaka', 'Chittagong', 'Sylhet', 'Rajshahi', 'Khulna', 'Barisal', 'Rangpur', 'Comilla', 'Gazipur', 'Narayanganj']
        warehouses = []
        for i in range(20):
            w, _ = Warehouse.objects.get_or_create(
                name=f"{random.choice(cities)} Shop {i+1}",
                code=f"WH{i+1:03d}",
                defaults={
                    'address': fake.address(),
                    'phone': fake.phone_number(),
                    'is_shop': random.choice([True, False])
                }
            )
            warehouses.append(w)
        self.stdout.write('Created 20 Warehouses.')

        # Categories
        cat_names = ['Wall Clock', 'Wrist Watch', 'Alarm Clock', 'Smartwatch', 'Pocket Watch', 'Grandfather Clock', 'Table Clock', 'Digital Clock', 'Stopwatch', 'Mantel Clock', 'Cuckoo Clock', 'Dive Watch', 'Dress Watch', 'Field Watch', 'Aviator Watch', 'Chronograph', 'Mechanical Watch', 'Quartz Watch', 'Automatic Watch', 'Luxury Watch']
        categories = []
        for i in range(20):
            c, _ = Category.objects.get_or_create(
                name=f"{cat_names[i]} - {i}",
                defaults={'description': fake_en.text()}
            )
            categories.append(c)
        self.stdout.write('Created 20 Categories.')

        # Brands
        brand_names = ['Casio', 'Seiko', 'Citizen', 'Rolex', 'Titan', 'Fastrack', 'Timex', 'Orient', 'Omax', 'Naviforce', 'Curren', 'Skmei', 'Apple', 'Samsung', 'Fossil', 'G-Shock', 'Q&Q', 'Romanson', 'Sonata', 'Tissot']
        brands = []
        for i in range(20):
            b, _ = Brand.objects.get_or_create(
                name=f"{brand_names[i]} - {i}",
                defaults={'description': fake_en.text()}
            )
            brands.append(b)
        self.stdout.write('Created 20 Brands.')

        # Products
        products = []
        for i in range(20):
            p, _ = Product.objects.get_or_create(
                sku=f"SKU{i+1000}",
                defaults={
                    'category': random.choice(categories),
                    'brand': random.choice(brands),
                    'description': fake_en.text(),
                    'default_selling_price': Decimal(random.randint(500, 15000))
                }
            )
            products.append(p)
        self.stdout.write('Created 20 Products.')

        # Purchases & Batches
        purchases = []
        batches = []
        for i in range(20):
            pur = Purchase.objects.create(
                supplier=f"Supplier {fake.company()}",
                purchase_date=fake.date_this_year(),
                total_amount=Decimal(random.randint(10000, 100000)),
                created_by=random.choice(users)
            )
            purchases.append(pur)
            
            # Purchase Item & Batch
            prod = random.choice(products)
            qty = random.randint(10, 100)
            unit_price = Decimal(random.randint(200, 10000))
            
            batch = Batch.objects.create(
                product=prod,
                warehouse=random.choice(warehouses),
                buy_price=unit_price,
                initial_quantity=qty,
                quantity=qty,
                purchase_date=pur.purchase_date,
                supplier=pur.supplier
            )
            batches.append(batch)
            
            PurchaseItem.objects.create(
                purchase=pur,
                batch=batch,
                product=prod,
                quantity=qty,
                unit_price=unit_price
            )
            prod.update_total_stock()
            
        self.stdout.write('Created 20 Purchases, PurchaseItems, and Batches.')

        # Customers
        customers = []
        for i in range(20):
            c, _ = Customer.objects.get_or_create(
                phone=f"017{random.randint(10000000, 99999999)}-{i}",
                defaults={
                    'name': fake.name(),
                    'email': fake_en.email(),
                    'address': fake.address(),
                    'credit_limit': Decimal(random.randint(0, 50000))
                }
            )
            customers.append(c)
        self.stdout.write('Created 20 Customers.')

        # Customer Notes
        for i in range(20):
            CustomerNote.objects.create(
                customer=random.choice(customers),
                note=fake_en.text(),
                created_by=random.choice(users)
            )
        self.stdout.write('Created 20 CustomerNotes.')

        # Sales & SaleItems
        sales = []
        sale_items = []
        for i in range(20):
            sale = Sale.objects.create(
                customer=random.choice(customers),
                sale_date=fake.date_time_this_year(tzinfo=timezone.get_current_timezone()),
                status='completed',
                created_by=random.choice(users)
            )
            sales.append(sale)
            
            # Sale Item
            batch = random.choice(batches)
            qty = random.randint(1, 5)
            if batch.quantity >= qty:
                batch.quantity -= qty
                batch.save()
                batch.product.update_total_stock()
                
                si = SaleItem.objects.create(
                    sale=sale,
                    product=batch.product,
                    batch=batch,
                    quantity=qty,
                    unit_price=batch.buy_price * Decimal('1.5'),
                    cost_price=batch.buy_price
                )
                sale_items.append(si)
            sale.calculate_totals()
            
        self.stdout.write('Created 20 Sales and SaleItems.')

        # Payments
        for i in range(20):
            sale = random.choice(sales)
            Payment.objects.create(
                customer=sale.customer,
                sale=sale,
                amount=sale.total_amount if sale.total_amount > 0 else Decimal('500.00'),
                payment_method=random.choice(['cash', 'card', 'mobile_payment']),
                received_by=random.choice(users)
            )
            sale.recalculate_paid_amount()
            sale.customer.recalculate_balance()
        self.stdout.write('Created 20 Payments.')

        # Sale Returns
        for i in range(20):
            if not sale_items:
                break
            sale = random.choice(sales)
            si = random.choice(sale.items.all() or sale_items) # just get a random item
            if not si.id: continue
            
            sr = SaleReturn.objects.create(
                sale=si.sale,
                return_date=fake.date_time_this_year(tzinfo=timezone.get_current_timezone()),
                reason="Defective",
                refund_amount=si.total_price,
                created_by=random.choice(users)
            )
            SaleReturnItem.objects.create(
                sale_return=sr,
                sale_item=si,
                quantity=1
            )
        self.stdout.write('Created 20 SaleReturns and SaleReturnItems.')

        # StockOuts
        for i in range(20):
            batch = random.choice(batches)
            if batch.quantity >= 1:
                so = StockOut.objects.create(
                    warehouse=batch.warehouse,
                    reason=random.choice(['damage', 'expired', 'loss']),
                    stockout_date=fake.date_time_this_year(tzinfo=timezone.get_current_timezone()),
                    created_by=random.choice(users),
                    status='completed'
                )
                
                batch.quantity -= 1
                batch.save()
                batch.product.update_total_stock()
                
                StockOutItem.objects.create(
                    stockout=so,
                    batch=batch,
                    quantity=1,
                    cost_price=batch.buy_price
                )
                
                so.total_value = batch.buy_price
                so.save()
        self.stdout.write('Created 20 StockOuts and StockOutItems.')

        # Stock Transfers
        for i in range(20):
            batch = random.choice(batches)
            if batch.quantity >= 1:
                dest = random.choice([w for w in warehouses if w != batch.warehouse])
                st = StockTransfer.objects.create(
                    source_warehouse=batch.warehouse,
                    destination_warehouse=dest,
                    transfer_date=fake.date_time_this_year(tzinfo=timezone.get_current_timezone()),
                    created_by=random.choice(users),
                    status='pending'
                )
                
                StockTransferItem.objects.create(
                    transfer=st,
                    source_batch=batch,
                    quantity=1
                )
                
                st.complete_transfer()
        self.stdout.write('Created 20 StockTransfers and StockTransferItems.')

        # AuditLogs (Optional, but let's make 20 if none were auto-created by signals)
        for i in range(20):
            AuditLog.objects.create(
                user=random.choice(users),
                action='CREATE',
                model_name='DummyModel',
                object_repr=f'Dummy {i}'
            )
        self.stdout.write('Created 20 AuditLogs.')

        self.stdout.write(self.style.SUCCESS('Successfully generated dummy data for all tables!'))
