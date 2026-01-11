"""
Management command to generate demo data fixture with 100 records per model.
Usage: python manage.py generate_demo_data
"""

import json
import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate demo data fixture with 100 records per model'

    def handle(self, *args, **options):
        fixtures = []
        
        # Bangladesh-specific data
        bd_cities = [
            ('Dhaka', 'DHK'), ('Chittagong', 'CTG'), ('Sylhet', 'SYL'), ('Rajshahi', 'RAJ'),
            ('Khulna', 'KHL'), ('Barishal', 'BAR'), ('Rangpur', 'RNG'), ('Mymensingh', 'MYM'),
            ('Comilla', 'COM'), ('Gazipur', 'GAZ'), ('Narayanganj', 'NAR'), ('Bogra', 'BOG'),
            ('Cox Bazar', 'COX'), ('Jessore', 'JES'), ('Dinajpur', 'DIN'), ('Brahmanbaria', 'BRA'),
            ('Tangail', 'TAN'), ('Narsingdi', 'NAR'), ('Savar', 'SAV'), ('Tongi', 'TON')
        ]
        
        bd_areas = [
            'Gulshan', 'Banani', 'Dhanmondi', 'Uttara', 'Mirpur', 'Mohammadpur', 'Motijheel',
            'Bashundhara', 'Badda', 'Khilgaon', 'Rampura', 'Tejgaon', 'Farmgate', 'Kawran Bazar',
            'Mohakhali', 'Baridhara', 'Nikunja', 'Pallabi', 'Shyamoli', 'Kalabagan'
        ]
        
        first_names = [
            'Mohammad', 'Abdul', 'Md', 'Sheikh', 'Kazi', 'Rafiq', 'Kamal', 'Jamal', 'Rahim', 'Karim',
            'Fatima', 'Ayesha', 'Khadija', 'Mariam', 'Sultana', 'Begum', 'Nasreen', 'Taslima', 'Hasina', 'Razia',
            'Habib', 'Rashid', 'Faruk', 'Masud', 'Hasan', 'Hussain', 'Imran', 'Tariq', 'Zahir', 'Nazrul',
            'Shirin', 'Kulsum', 'Halima', 'Amina', 'Salma', 'Rehana', 'Monira', 'Jesmin', 'Parvin', 'Rahima'
        ]
        
        last_names = [
            'Rahman', 'Islam', 'Hossain', 'Ahmed', 'Alam', 'Uddin', 'Khan', 'Chowdhury', 'Miah', 'Sarker',
            'Begum', 'Khatun', 'Akter', 'Sultana', 'Khanam', 'Banu', 'Jahan', 'Nahar', 'Bibi', 'Nessa',
            'Ali', 'Haque', 'Kabir', 'Malik', 'Siddique', 'Molla', 'Sheikh', 'Talukder', 'Bhuiyan', 'Mondal'
        ]
        
        watch_brands = [
            ('Casio', 'Japanese electronics'), ('Seiko', 'Japanese luxury'), ('Citizen', 'Japanese eco-drive'),
            ('Titan', 'Indian premium'), ('Fastrack', 'Youth fashion'), ('Sonata', 'Budget friendly'),
            ('Orient', 'Japanese classic'), ('Rhythm', 'Wall clocks specialist'), ('Q&Q', 'Affordable quality'),
            ('Timex', 'American classic'), ('Fossil', 'Fashion watches'), ('Michael Kors', 'Designer'),
            ('Guess', 'Fashion brand'), ('Tommy Hilfiger', 'American style'), ('Armani Exchange', 'Italian design'),
            ('Diesel', 'Bold designs'), ('Swatch', 'Swiss colorful'), ('Rado', 'Swiss ceramic'),
            ('Tissot', 'Swiss tradition'), ('Longines', 'Swiss elegance')
        ]
        
        categories = [
            ('Wall Clocks', 'Decorative and functional wall clocks'),
            ('Table Clocks', 'Desktop and bedside clocks'),
            ('Wrist Watches - Men', 'Watches for men'),
            ('Wrist Watches - Women', 'Watches for women'),
            ('Wrist Watches - Unisex', 'Gender-neutral watches'),
            ('Smart Watches', 'Digital smart watches'),
            ('Alarm Clocks', 'Wake-up alarm clocks'),
            ('Grandfather Clocks', 'Traditional standing clocks'),
            ('Cuckoo Clocks', 'Decorative cuckoo clocks'),
            ('Digital Clocks', 'LED/LCD display clocks'),
            ('Pocket Watches', 'Classic pocket watches'),
            ('Sports Watches', 'Activity and sports watches'),
            ('Luxury Watches', 'Premium luxury timepieces'),
            ('Kids Watches', 'Watches for children'),
            ('Couple Watches', 'Matching pair watches')
        ]
        
        product_types = [
            ('Wall Clock', 'WC', (1500, 8000)),
            ('Table Clock', 'TC', (800, 3500)),
            ('Analog Watch', 'AW', (2000, 15000)),
            ('Digital Watch', 'DW', (1500, 8000)),
            ('Smart Watch', 'SW', (3000, 25000)),
            ('Alarm Clock', 'AC', (500, 2000)),
            ('Sports Watch', 'SP', (2500, 12000)),
            ('Luxury Watch', 'LW', (15000, 50000)),
            ('Kids Watch', 'KW', (500, 2500)),
            ('Pocket Watch', 'PW', (1000, 5000))
        ]
        
        payment_methods = ['cash', 'bkash', 'nagad', 'bank', 'card']
        
        # Generate Warehouses (20)
        for i in range(1, 21):
            city, code = bd_cities[i-1] if i <= len(bd_cities) else (f'City {i}', f'C{i:02d}')
            fixtures.append({
                "model": "warehouse.warehouse",
                "pk": i,
                "fields": {
                    "name": f"{city} Branch",
                    "code": code,
                    "address": f"{random.choice(bd_areas)}, {city}",
                    "phone": f"01{random.randint(3,9)}{random.randint(10000000, 99999999)}",
                    "is_active": True
                }
            })
        
        # Generate Categories (15)
        for i, (name, desc) in enumerate(categories, 1):
            fixtures.append({
                "model": "inventory.category",
                "pk": i,
                "fields": {
                    "name": name,
                    "description": desc
                }
            })
        
        # Generate Brands (20)
        for i, (name, desc) in enumerate(watch_brands, 1):
            fixtures.append({
                "model": "inventory.brand",
                "pk": i,
                "fields": {
                    "name": name,
                    "description": desc
                }
            })
        
        # Generate Products (100)
        for i in range(1, 101):
            ptype, prefix, price_range = random.choice(product_types)
            brand_id = random.randint(1, 20)
            cat_id = random.randint(1, 15)
            base_price = random.randint(price_range[0], price_range[1])
            
            fixtures.append({
                "model": "inventory.product",
                "pk": i,
                "fields": {
                    "name": f"{watch_brands[brand_id-1][0]} {ptype} {i:03d}",
                    "sku": f"{prefix}-{i:04d}",
                    "category": cat_id,
                    "brand": brand_id,
                    "description": f"High quality {ptype.lower()} from {watch_brands[brand_id-1][0]}",
                    "default_selling_price": str(base_price),
                    "is_active": True
                }
            })
        
        # Generate Customers (100)
        for i in range(1, 101):
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            city, _ = random.choice(bd_cities)
            area = random.choice(bd_areas)
            
            fixtures.append({
                "model": "customers.customer",
                "pk": i,
                "fields": {
                    "name": f"{fname} {lname}",
                    "phone": f"01{random.randint(3,9)}{random.randint(10000000, 99999999)}",
                    "email": f"{fname.lower()}.{lname.lower()}{i}@email.com" if random.random() > 0.5 else "",
                    "address": f"House {random.randint(1,500)}, Road {random.randint(1,30)}, {area}, {city}",
                    "total_due": "0.00",
                    "created_at": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat()
                }
            })
        
        # Generate Batches (100)
        for i in range(1, 101):
            product_id = ((i - 1) % 100) + 1
            warehouse_id = random.randint(1, 20)
            buy_price = random.randint(500, 20000)
            quantity = random.randint(5, 100)
            purchase_date = (datetime.now() - timedelta(days=random.randint(1, 180))).date()
            
            fixtures.append({
                "model": "inventory.batch",
                "pk": i,
                "fields": {
                    "product": product_id,
                    "warehouse": warehouse_id,
                    "batch_number": f"BTH-{purchase_date.strftime('%Y%m')}-{i:04d}",
                    "quantity": quantity,
                    "buy_price": str(buy_price),
                    "purchase_date": purchase_date.isoformat(),
                    "supplier_name": f"Supplier {random.choice(['A', 'B', 'C', 'D', 'E'])}{random.randint(1,20)}",
                    "notes": ""
                }
            })
        
        # Generate Sales (100)
        base_date = datetime.now()
        for i in range(1, 101):
            customer_id = random.randint(1, 100) if random.random() > 0.2 else None
            sale_date = base_date - timedelta(days=random.randint(0, 90), hours=random.randint(9, 20))
            status = random.choice(['completed', 'completed', 'completed', 'cancelled'])
            total = random.randint(1000, 50000)
            
            if status == 'completed':
                payment_status = random.choice(['paid', 'paid', 'paid', 'partial', 'unpaid'])
                if payment_status == 'paid':
                    paid = total
                elif payment_status == 'partial':
                    paid = random.randint(int(total * 0.3), int(total * 0.8))
                else:
                    paid = 0
            else:
                payment_status = 'unpaid'
                paid = 0
            
            fixtures.append({
                "model": "sales.sale",
                "pk": i,
                "fields": {
                    "invoice_number": f"INV-{sale_date.strftime('%Y%m')}-{i:04d}",
                    "customer": customer_id,
                    "sale_date": sale_date.isoformat(),
                    "total_amount": str(total),
                    "total_cost": str(int(total * 0.6)),
                    "discount_amount": str(random.randint(0, int(total * 0.1))),
                    "paid_amount": str(paid),
                    "payment_status": payment_status,
                    "status": status,
                    "notes": "",
                    "created_by": 1
                }
            })
        
        # Generate Sale Items (200 - ~2 items per sale)
        for i in range(1, 201):
            sale_id = ((i - 1) // 2) + 1
            if sale_id > 100:
                sale_id = random.randint(1, 100)
            
            product_id = random.randint(1, 100)
            batch_id = random.randint(1, 100)
            quantity = random.randint(1, 5)
            unit_price = random.randint(1000, 20000)
            cost_price = int(unit_price * 0.6)
            
            fixtures.append({
                "model": "sales.saleitem",
                "pk": i,
                "fields": {
                    "sale": sale_id,
                    "product": product_id,
                    "batch": batch_id,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "cost_price": str(cost_price),
                    "discount": "0.00",
                    "is_custom": False,
                    "custom_description": ""
                }
            })
        
        # Generate Payments (100)
        for i in range(1, 101):
            sale_id = i
            payment_date = (datetime.now() - timedelta(days=random.randint(0, 60))).isoformat()
            amount = random.randint(500, 30000)
            method = random.choice(payment_methods)
            
            if method == 'bank':
                ref = f"TXN{random.randint(100000, 999999)}"
            elif method in ['bkash', 'nagad']:
                ref = f"01{random.randint(300000000, 999999999)}"
            else:
                ref = ""
            
            fixtures.append({
                "model": "customers.payment",
                "pk": i,
                "fields": {
                    "sale": sale_id,
                    "customer": random.randint(1, 100),
                    "amount": str(amount),
                    "payment_method": method,
                    "payment_date": payment_date,
                    "reference": ref,
                    "notes": ""
                }
            })
        
        # Generate Stock Transfers (50)
        for i in range(1, 51):
            from_wh = random.randint(1, 20)
            to_wh = random.randint(1, 20)
            while to_wh == from_wh:
                to_wh = random.randint(1, 20)
            
            transfer_date = (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat()
            
            fixtures.append({
                "model": "warehouse.stocktransfer",
                "pk": i,
                "fields": {
                    "from_warehouse": from_wh,
                    "to_warehouse": to_wh,
                    "transfer_date": transfer_date,
                    "status": random.choice(['completed', 'completed', 'pending']),
                    "notes": f"Transfer #{i}",
                    "created_by": 1
                }
            })
        
        # Generate Transfer Items (100)
        for i in range(1, 101):
            transfer_id = ((i - 1) // 2) + 1
            if transfer_id > 50:
                transfer_id = random.randint(1, 50)
            
            fixtures.append({
                "model": "warehouse.transferitem",
                "pk": i,
                "fields": {
                    "transfer": transfer_id,
                    "batch": random.randint(1, 100),
                    "quantity": random.randint(1, 20)
                }
            })
        
        # Write to file
        output_path = 'fixtures/demo_data.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(fixtures, f, indent=2, ensure_ascii=False)
        
        self.stdout.write(self.style.SUCCESS(f'Successfully generated demo data to {output_path}'))
        self.stdout.write(f'Total records: {len(fixtures)}')
