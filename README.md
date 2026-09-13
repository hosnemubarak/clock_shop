# Clock Shop - Inventory & Sales Management System

A comprehensive, production-ready Inventory and Sales Management System for retail clock/watch shops. Built with Django 4.2 and Bootstrap 5 (Invoika template), designed specifically for the Bangladesh market with BDT (৳) currency support.

![Django](https://img.shields.io/badge/Django-4.2-green.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Deployment Options](#deployment-options)
  - [Option 1: Local Development (SQLite)](#option-1-local-development-sqlite)
  - [Option 2: Docker Deployment (PostgreSQL)](#option-2-docker-deployment-postgresql)
  - [Option 3: Linux Server (Production)](#option-3-linux-server-production)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Key Workflows](#key-workflows)
- [Admin Panel](#admin-panel)
- [Demo Data](#demo-data)
- [API Endpoints](#api-endpoints)
- [Contributing](#contributing)

## Overview

Clock Shop is a full-featured business management solution that handles:
- **Inventory tracking** with batch-based stock management
- **Point of Sale (POS)** with invoice generation
- **Customer relationship management** with credit tracking
- **Multi-warehouse operations** with stock transfers
- **Comprehensive reporting** with visual charts
- **Stock out management** for damaged/lost/expired items
- **Complete audit trail** for all operations

## Features

### Inventory Management
- **Multi-warehouse support** - Manage stock across multiple warehouses and shop locations
- **Batch-based tracking** - Each purchase creates a separate batch with its own buy price
- **Multiple purchase prices** - Same product can have different costs from different batches
- **Low stock alerts** - Automatic alerts for products below configurable threshold
- **Stock Out** - Track damaged, lost, expired, or internally used inventory

### Sales Management
- **Manual batch selection** - User selects specific batch when selling
- **Custom items** - Add non-inventory items (old dues, services, etc.)
- **Stock validation** - Prevents overselling beyond batch quantity
- **Automatic COGS calculation** - Cost of Goods Sold tracked per sale
- **Profit tracking** - Per sale, product, and warehouse profit reports
- **Invoice generation** - Print-ready invoices with thermal printer support

### Customer Management
- **Customer profiles** - Name, phone, email, address, purchase history
- **Credit tracking** - Outstanding dues per customer with credit limits
- **Payment management** - Partial and multiple payments per invoice
- **Customer statements** - Detailed transaction history
- **Customer notes** - Internal notes and communication tracking

### Warehouse & Stock Transfer
- **Multiple warehouses** - Support for warehouses and retail shop locations
- **Batch-level transfers** - Transfer specific batches between locations
- **Price preservation** - Original buy price maintained during transfers
- **Full audit trail** - Complete transfer history with status tracking

### Reporting & Analytics
- **Dashboard** - Real-time KPIs with interactive charts (ApexCharts)
- **Sales reports** - Daily, weekly, monthly sales analysis with visualizations
- **Profit reports** - By product, category, warehouse, and time period
- **Stock reports** - Current inventory levels, valuation, and aging
- **Customer reports** - Outstanding dues, top customers, payment history
- **Dead stock analysis** - Identify slow-moving inventory
- **Batch analysis** - Stock age and batch-level tracking
- **Transfer history** - Complete inter-warehouse movement records

### Security & Audit
- **Login required** - All views protected by authentication
- **User registration** - With admin approval workflow
- **Audit logging** - Track all create, update, delete operations
- **CSRF protection** - Django's built-in CSRF with configurable trusted origins

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Django 4.2 (Python 3.10+) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | Bootstrap 5.3, Invoika Template |
| Charts | ApexCharts |
| Icons | Line Awesome, Remix Icons |
| CSS | Custom + Bootstrap |
| Static Files | WhiteNoise |
| Server | Gunicorn (production) |

## Quick Start

Choose your deployment method:

| Method | Database | Best For |
|--------|----------|----------|
| **Local Development** | SQLite | Development, testing |
| **Docker** | PostgreSQL | Production, easy deployment |
| **Linux Server** | PostgreSQL/SQLite | Custom production setup |

---

## Deployment Options

### Option 1: Local Development (SQLite)

Simple setup for development and testing. Uses SQLite database (no external database required).

```bash
# 1. Clone and navigate to project
cd clock_shop

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Copy environment file
cp .env.example .env

# 6. Run migrations
python manage.py migrate

# 7. Create admin user
python manage.py createsuperuser

# 8. (Optional) Load demo data
python manage.py loaddata fixtures/demo_data.json

# 9. Start development server
python manage.py runserver
```

**Access:** http://127.0.0.1:8000

---

### Option 2: Docker Deployment (PostgreSQL)

Production-ready deployment using Docker with PostgreSQL database. **Recommended for production.**

#### Prerequisites
- Docker & Docker Compose installed

#### Quick Deploy

```bash
# 1. Clone and navigate to project
cd clock_shop

# 2. Copy and configure environment
cp .env.example .env

# 3. Edit .env file (IMPORTANT: Change SECRET_KEY!)
nano .env
```

**Minimum .env configuration for Docker:**
```env
SECRET_KEY=your-super-secure-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
CSRF_TRUSTED_ORIGINS=http://localhost:8090,https://your-domain.com
SHOP_NAME=Your Shop Name
POSTGRES_PASSWORD=strong-database-password
```

```bash
# 4. Build and start containers
docker-compose up -d --build

# 5. Create admin user
docker-compose exec web python manage.py createsuperuser

# 6. (Optional) Load demo data
docker-compose exec web python manage.py loaddata fixtures/demo_data.json
```

**Access:** http://localhost:8090

#### Docker Commands

```bash
# View logs
docker-compose logs -f web

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Restart services
docker-compose restart

# Enter container shell
docker-compose exec web bash

# Database backup
docker-compose exec db pg_dump -U clock_shop clock_shop > backup.sql
```

---

### Option 3: Linux Server (Production)

Manual deployment on a Linux server with Gunicorn. Suitable for VPS/Cloud deployment.

#### Prerequisites
- Ubuntu 20.04+ / Debian 11+
- Python 3.10+
- PostgreSQL (optional, SQLite works too)

#### Step 1: System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv git

# (Optional) Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib libpq-dev
```

#### Step 2: PostgreSQL Setup (Optional)

```bash
# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE clock_shop;
CREATE USER clock_shop WITH PASSWORD 'your-secure-password';
ALTER ROLE clock_shop SET client_encoding TO 'utf8';
ALTER ROLE clock_shop SET default_transaction_isolation TO 'read committed';
ALTER ROLE clock_shop SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE clock_shop TO clock_shop;
EOF
```

#### Step 3: Application Setup

```bash
# Clone repository
git clone <your-repo-url> /opt/clock_shop
cd /opt/clock_shop

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
nano .env
```

**Production .env configuration:**
```env
SECRET_KEY=your-very-long-and-secure-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# For PostgreSQL:
DATABASE_URL=postgres://clock_shop:your-secure-password@localhost:5432/clock_shop

# Or leave empty for SQLite (simpler)

CSRF_TRUSTED_ORIGINS=https://your-domain.com
SHOP_NAME=Your Clock Shop
CURRENCY_SYMBOL=৳
```

```bash
# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create admin user
python manage.py createsuperuser
```

#### Step 4: Systemd Service

```bash
# Create service file
sudo nano /etc/systemd/system/clockshop.service
```

```ini
[Unit]
Description=Clock Shop Django Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/clock_shop
EnvironmentFile=/opt/clock_shop/.env
ExecStart=/opt/clock_shop/venv/bin/gunicorn clock_shop.wsgi:application --bind 0.0.0.0:8000 --workers 3
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
# Set permissions
sudo chown -R www-data:www-data /opt/clock_shop

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable clockshop
sudo systemctl start clockshop

# Check status
sudo systemctl status clockshop
```

**Access:** http://your-server-ip:8000

---

## Initial Data Setup

After deployment, you can:

### Load Demo Data (Recommended for Testing)
```bash
# Local
python manage.py loaddata fixtures/demo_data.json

# Docker
docker-compose exec web python manage.py loaddata fixtures/demo_data.json
```

Demo data includes:
- **1 Category** - Clocks
- **1 Brand** - Seiko
- **1 Warehouse** - Main Warehouse (WH001)
- **1 Retail Shop** - Retail Shop (RS001)
- **1 Product** - Classic Wall Clock (CLK-001)
- **1 Customer** - Sample Customer

### Start Fresh
1. Create Warehouses/Shop locations
2. Add Product Categories
3. Add Brands (optional)
4. Create Products
5. Stock In - Add initial inventory

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

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### All Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (insecure) | Django secret key - **MUST change in production** |
| `DEBUG` | `True` | Debug mode - Set to `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8090` | CSRF trusted origins with protocol |
| `DATABASE_URL` | (empty) | PostgreSQL URL (if empty, uses SQLite) |
| `DB_ENGINE` | (empty) | Set to `postgresql` for PostgreSQL |
| `DB_NAME` | `clock_shop` | Database name |
| `DB_USER` | `clock_shop` | Database user |
| `DB_PASSWORD` | (empty) | Database password |
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `5432` | Database port |
| `SHOP_NAME` | `Clock Shop` | Business name |
| `CURRENCY_SYMBOL` | `৳` | Currency symbol |
| `LOW_STOCK_THRESHOLD` | `5` | Low stock alert threshold |
| `POSTGRES_DB` | `clock_shop` | Docker PostgreSQL database |
| `POSTGRES_USER` | `clock_shop` | Docker PostgreSQL user |
| `POSTGRES_PASSWORD` | (required) | Docker PostgreSQL password |
| `APP_PORT` | `8090` | Application port (Docker) |

### Database Configuration

**SQLite (Default - Local Development):**
```env
# Leave DATABASE_URL and DB_* variables empty
```

**PostgreSQL (Docker/Production):**
```env
# Option 1: DATABASE_URL
DATABASE_URL=postgres://user:password@host:5432/dbname

# Option 2: Individual variables
DB_ENGINE=postgresql
DB_NAME=clock_shop
DB_USER=clock_shop
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
```

## Customization

### Shop Settings
Configure via `.env` file:
```env
SHOP_NAME=Your Clock Shop Name
CURRENCY_SYMBOL=৳
LOW_STOCK_THRESHOLD=10
```

### Backup & Restore

```bash
# SQLite backup
cp db.sqlite3 backup_$(date +%Y%m%d).sqlite3

# PostgreSQL backup (Docker)
docker-compose exec db pg_dump -U clock_shop clock_shop > backup.sql

# PostgreSQL restore (Docker)
cat backup.sql | docker-compose exec -T db psql -U clock_shop clock_shop

# Export data as JSON
python manage.py dumpdata > backup.json

# Import data from JSON
python manage.py loaddata backup.json
```

### Payment Methods Supported
- **Cash** - Direct cash payments
- **Mobile Payment** - bKash, Nagad
- **Bank Transfer** - DBBL, BRAC, UCB, and other banks
- **Card** - Visa, Mastercard

## Admin Panel

The Django admin panel is fully configured with:

- **List displays** - Key fields visible at a glance
- **Search fields** - Quick search across relevant fields
- **Filters** - Filter by status, date, warehouse, etc.
- **Date hierarchy** - Navigate by date for time-based models
- **Inline editing** - View related items directly
- **Status badges** - Color-coded status indicators
- **Fieldsets** - Organized field groupings

Access at: `http://localhost:8000/admin/`

## API Endpoints

Internal API endpoints for AJAX operations:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/inventory/api/products/<id>/batches/` | GET | Get batches for a product |
| `/inventory/api/warehouses/<id>/batches/` | GET | Get batches in a warehouse |
| `/sales/api/batch/<id>/` | GET | Get batch details |
| `/customers/api/<id>/invoices/` | GET | Get customer's unpaid invoices |

## Screenshots

### Dashboard
- Real-time statistics cards
- Sales trend chart (6 months)
- Payment status donut chart
- Recent sales and low stock alerts

### Sales
- POS-style sale creation
- Batch selection with stock info
- Invoice printing
- Payment tracking

### Reports
- Interactive charts
- Date range filtering
- Export capabilities

## Logging

The application includes a professional logging system with:

| Log File | Description |
|----------|-------------|
| `logs/app.log` | General application logs |
| `logs/error.log` | Errors and exceptions only |
| `logs/security.log` | Authentication and security events |
| `logs/db.log` | Database queries (DEBUG mode only) |

**Features:**
- Rotating file handlers (5MB max, 5 backups)
- Structured log formatting with timestamps
- Separate loggers for each app module
- Console output in development, file-based in production

## Dependencies

```
Django>=4.2,<5.0
Pillow>=10.0.0
whitenoise>=6.6.0
python-dotenv>=1.0.0
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project uses the Invoika HTML template. Ensure you have a valid license for the template.

The application code is provided under the MIT License.

## Support

For issues and questions, please create an issue in the repository.

---

**Built with ❤️ for Bangladesh retail businesses**
