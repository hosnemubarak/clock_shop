# Clock Shop - Inventory & Sales Management System

A production-ready Inventory and Sales Management System for a retail clock shop built with Django and SQLite, using the Invoika HTML template. Designed for the Bangladesh market with BDT (৳) currency support.

![Django](https://img.shields.io/badge/Django-4.2-green.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

### Inventory Management
- **Multi-warehouse support** - Manage stock across multiple warehouses and shop locations
- **Batch-based tracking** - Each purchase creates a separate batch with its own buy price
- **Multiple purchase prices** - Same product can have different costs from different batches
- **Low stock alerts** - Automatic alerts for products below threshold

### Sales Management
- **Manual batch selection** - User selects specific batch when selling
- **Stock validation** - Prevents overselling beyond batch quantity
- **Automatic COGS calculation** - Cost of Goods Sold tracked per sale
- **Profit tracking** - Per sale, product, and warehouse profit reports
- **Invoice generation** - Print-ready invoices

### Customer Management
- **Customer profiles** - Name, phone, address, purchase history
- **Credit tracking** - Outstanding dues per customer
- **Payment management** - Partial and multiple payments per invoice
- **Customer statements** - Detailed transaction history

### Warehouse & Stock Transfer
- **Multiple warehouses** - Support for warehouses and retail shop locations
- **Batch-level transfers** - Transfer specific batches between locations
- **Price preservation** - Original buy price maintained during transfers
- **Full audit trail** - Complete transfer history

### Reporting & Analytics
- **Sales reports** - Daily, weekly, monthly sales analysis
- **Profit reports** - By product, category, and warehouse
- **Stock reports** - Current inventory levels and valuation
- **Customer reports** - Outstanding dues, top customers
- **Dead stock analysis** - Identify slow-moving inventory
- **Batch analysis** - Stock age and batch tracking

## Installation

### Prerequisites
- Python 3.10+
- pip

### Setup

1. **Navigate to project directory:**
```bash
cd clock_shop
```

2. **Create virtual environment:**
```bash
python -m venv venv
```

3. **Activate virtual environment:**
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

4. **Install dependencies:**
```bash
pip install -r requirements.txt
```

5. **Copy static files from Invoika template:**
```bash
# Copy the assets folder from invoika/layouts/assets to clock_shop/static/
# This includes CSS, JS, images, and fonts
```

6. **Run migrations:**
```bash
python manage.py migrate
```

7. **Create superuser:**
```bash
python manage.py createsuperuser
```

8. **Load demo data (optional):**
```bash
python manage.py loaddata fixtures\demo_data.json
```

9. **Run development server:**
```bash
python manage.py runserver
```

10. **Access the application:**
- Main app: http://127.0.0.1:8000/
- Admin panel: http://127.0.0.1:8000/admin/

## Initial Setup

After installation, you can either:

### Option 1: Load Demo Data (Recommended for Testing)
```bash
python manage.py loaddata fixtures\demo_data.json
```

This loads realistic Bangladesh-based sample data including:
- **10 Warehouses** - Gulshan, Banani, Dhanmondi, Uttara, Chittagong, Sylhet, Rajshahi, Khulna, Gazipur, Mirpur
- **10 Categories** - Wall Clocks, Table Clocks, Wrist Watches, Alarm Clocks, Smart Watches, etc.
- **10 Brands** - Casio, Seiko, Citizen, Titan, Xiaomi, Rhythm, Orient, Sonata, Q&Q, Fastrack
- **10 Products** - With realistic BDT prices (৳950 - ৳12,500)
- **10 Customers** - Bangladesh addresses and phone numbers (01XXX-XXXXXX format)
- **10 Batches** - Stock with buy prices
- **10 Sales** - Sample invoices with various payment statuses
- **10 Payments** - Cash, bKash, Nagad, Bank Transfer (DBBL, BRAC, UCB)

**Note:** Demo data includes a default admin user. Create your own superuser after loading.

### Option 2: Start Fresh
1. **Create Warehouses** - Add at least one warehouse/shop location
2. **Create Categories** - Add product categories (e.g., Wall Clocks, Table Clocks, etc.)
3. **Create Brands** - Add clock brands (optional)
4. **Add Products** - Create your product catalog
5. **Stock In** - Add initial inventory using the "Stock In" feature

## Project Structure

```
clock_shop/
├── apps/
│   ├── core/           # Dashboard, authentication, audit logs
│   ├── inventory/      # Products, batches, categories, purchases
│   ├── sales/          # Sales, invoices, POS
│   ├── customers/      # Customer management, payments
│   ├── warehouse/      # Warehouses, stock transfers
│   └── reports/        # All reporting modules
├── templates/          # Django templates (Invoika-based)
├── static/            # CSS, JS, images
├── clock_shop/        # Django project settings
├── manage.py
└── requirements.txt
```

## Key Workflows

### Purchase → Sale → Payment → Profit

1. **Purchase/Stock In:**
   - Add products to inventory via batch creation
   - Each batch has: product, warehouse, buy price, quantity, purchase date

2. **Sale:**
   - Create sale and manually select batches for each item
   - System validates stock availability
   - Stock automatically deducted from selected batch
   - Invoice generated with full details

3. **Payment:**
   - Record partial or full payments against invoices
   - Customer balance automatically updated
   - Payment history maintained

4. **Profit Calculation:**
   - Profit = Selling Price - Cost Price (from batch)
   - Reports show profit by product, category, warehouse

## Business Rules

- **Batch Selection:** Sales require manual batch selection (not automatic FIFO/LIFO)
- **Stock Validation:** Cannot sell more than available in selected batch
- **Price Independence:** Selling price can differ from buy price
- **Batch Permanence:** Sale records permanently store batch reference
- **Transfer Integrity:** Transfers preserve original batch buy price

## Security Features

- Django's built-in CSRF protection
- Login required for all views
- Audit logging for all major actions
- Permission-based access (extensible)

## Production Deployment

### Using Docker (Recommended)

1. **Build and run with Docker Compose:**
```bash
docker-compose up -d --build
```

2. **Create superuser (first time only):**
```bash
docker-compose exec web python manage.py createsuperuser
```

3. **Access the application:**
- Main app: http://localhost:8000/
- Admin panel: http://localhost:8000/admin/

### Linux Deployment (Manual)

1. **Update system and install dependencies:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git -y
```

2. **Clone the repository:**
```bash
git clone <your-repo-url> clock_shop
cd clock_shop
```

3. **Create and activate virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

4. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

5. **Set environment variables:**
```bash
export SECRET_KEY='your-secure-secret-key-here'
export DEBUG=False
export ALLOWED_HOSTS='127.0.0.1,localhost'
export SHOP_NAME='Your Shop Name'
export CURRENCY_SYMBOL='৳'
export LOW_STOCK_THRESHOLD=10
```

6. **Run migrations and collect static files:**
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

7. **Create superuser:**
```bash
python manage.py createsuperuser
```

8. **Run with Gunicorn:**
```bash
gunicorn clock_shop.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

### Using Systemd Service (Production)

1. **Create service file:**
```bash
sudo nano /etc/systemd/system/clockshop.service
```

2. **Add service configuration:**
```ini
[Unit]
Description=Clock Shop Django Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/clock_shop
Environment="SECRET_KEY=your-secret-key"
Environment="DEBUG=False"
Environment="ALLOWED_HOSTS=your-domain.com"
ExecStart=/path/to/clock_shop/venv/bin/gunicorn clock_shop.wsgi:application --bind 127.0.0.1:8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

3. **Enable and start service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable clockshop
sudo systemctl start clockshop
```

### Nginx Configuration (Optional)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /static/ {
        alias /path/to/clock_shop/staticfiles/;
    }

    location /media/ {
        alias /path/to/clock_shop/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (insecure default) | Django secret key - **MUST change in production** |
| `DEBUG` | `True` | Enable debug mode - Set to `False` in production |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | `http://127.0.0.1:*,http://localhost:*` | Comma-separated CSRF trusted origins |
| `SHOP_NAME` | `Clock Shop` | Business name |
| `CURRENCY_SYMBOL` | `৳` | Currency symbol (BDT) |
| `LOW_STOCK_THRESHOLD` | `5` | Low stock alert threshold |

### CSRF Configuration

The `CSRF_TRUSTED_ORIGINS` setting is crucial for forms to work correctly:

**Local Development:**
```env
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:*,http://localhost:*
```

**Production (HTTPS):**
```env
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**Multiple Origins:**
```env
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com,https://admin.yourdomain.com
```

## Customization

### Shop Settings
Configure via environment variables or edit `clock_shop/settings.py`:
```python
SHOP_NAME = "Your Clock Shop Name"
CURRENCY_SYMBOL = "৳"  # BDT - Bangladeshi Taka
LOW_STOCK_THRESHOLD = 10
```

### Demo Data
The `fixtures/demo_data.json` file contains sample data for testing. You can:
- Modify it to match your business needs
- Use it as a template to create your own fixture
- Export your data using: `python manage.py dumpdata > backup.json`

### Adding Custom Reports
Add new views in `apps/reports/views.py` and register URLs in `apps/reports/urls.py`

## Demo Data Details

| Model | Records | Description |
|-------|---------|-------------|
| Warehouse | 10 | Major cities across Bangladesh |
| Category | 10 | Clock and watch categories |
| Brand | 10 | Popular watch brands |
| Product | 10 | Watches and clocks with SKUs |
| Customer | 10 | BD phone numbers and addresses |
| Batch | 10 | Stock batches with suppliers |
| Sale | 10 | Sample invoices |
| SaleItem | 10 | Line items for sales |
| Payment | 10 | Various payment methods |

### Payment Methods Supported
- **Cash** - Direct cash payments
- **Mobile Payment** - bKash, Nagad
- **Bank Transfer** - DBBL, BRAC, UCB, and other banks
- **Card** - Visa, Mastercard

## Dependencies

- **Django 4.2** - Web framework
- **Pillow** - Image processing
- **Whitenoise** - Static file serving
- **Gunicorn** - WSGI HTTP server

## License

This project uses the Invoika HTML template. Ensure you have a valid license for the template.

## Support

For issues and questions, please create an issue in the repository.
