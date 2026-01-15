# cPanel Quick Start Guide

**Quick reference for deploying Clock Shop on cPanel with PostgreSQL**

---

## 🚀 Quick Steps

### 1. Create PostgreSQL Database (cPanel)
```
PostgreSQL Databases → Create Database: clock_shop_db
PostgreSQL Databases → Create User: clock_shop_user (strong password)
PostgreSQL Databases → Add User to Database (ALL PRIVILEGES)
```
**Note:** cPanel will prefix with your username (e.g., `rumaelec_clock_shop_db`)

---

### 2. Upload Files
```bash
# Compress locally (exclude unnecessary files)
zip -r clock_shop.zip . -x "*.git*" -x "*__pycache__*" -x "*.pyc" -x "db.sqlite3" -x ".venv/*"

# Upload to cPanel File Manager → Extract to ~/clock_shop
```

---

### 3. Setup Python App (cPanel)
```
Setup Python App → Create Application
- Python: 3.11
- App Root: /home/username/clock_shop
- App URL: yourdomain.com
- Startup: passenger_wsgi.py
- Entry: application
```

---

### 4. Install Dependencies (SSH/Terminal)
```bash
source ~/virtualenv/clock_shop/3.11/bin/activate
cd ~/clock_shop
pip install -r requirements.txt
```

---

### 5. Configure Environment
```bash
cd ~/clock_shop
cp .env.cpanel .env
nano .env
```

**Update these values:**
```env
SECRET_KEY=<generate-new-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com

DB_ENGINE=postgresql
DB_NAME=rumaelec_clock_shop_db
DB_USER=rumaelec_clock_shop_user
DB_PASSWORD=<your-db-password>
DB_HOST=localhost
DB_PORT=5432
```

**Generate SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

### 6. Update Config Files
```bash
# Update passenger_wsgi.py - replace YOUR_CPANEL_USERNAME
nano ~/clock_shop/passenger_wsgi.py

# Update .htaccess - replace YOUR_CPANEL_USERNAME
nano ~/clock_shop/.htaccess
```

---

### 7. Setup Django
```bash
cd ~/clock_shop
source ~/virtualenv/clock_shop/3.11/bin/activate

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Create admin user (if you have SSH access)
python manage.py createsuperuser
```

**No SSH Access?** See `CREATE_ADMIN_WITHOUT_SSH.md` for alternative methods:
- Use `create_admin.py` script via cPanel Python App
- Or use temporary Django view method

---

### 8. Restart & Test
```bash
# Restart app
touch ~/clock_shop/tmp/restart.txt

# Or use cPanel: Setup Python App → Restart
```

**Visit:** `https://yourdomain.com`

---

## ⚡ Common Commands

### Update Application
```bash
cd ~/clock_shop
source ~/virtualenv/clock_shop/3.11/bin/activate
git pull  # or upload new files
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch ~/clock_shop/tmp/restart.txt
```

### Backup Database
```bash
pg_dump -U rumaelec_clock_shop_user -h localhost rumaelec_clock_shop_db > backup.sql
```

### View Logs
```bash
tail -f ~/logs/error_log
```

---

## 🔧 Troubleshooting

**App won't start?**
- Check Python version: `python --version`
- Check virtual env: `which python`
- Verify .env file exists and is correct

**Database errors?**
- Test connection: `psql -U rumaelec_clock_shop_user -d rumaelec_clock_shop_db -h localhost`
- Verify credentials in .env
- Check PostgreSQL is running: `pg_isready -h localhost`

**Static files missing?**
- Re-run: `python manage.py collectstatic --clear --noinput`
- Check permissions: `chmod -R 755 ~/clock_shop/staticfiles/`

**500 Error?**
- Check logs: `tail -f ~/logs/error_log`
- Temporarily enable DEBUG=True to see detailed errors

---

## 📋 Checklist

- [ ] PostgreSQL database created
- [ ] Database user created with ALL PRIVILEGES
- [ ] Files uploaded to ~/clock_shop
- [ ] Python app configured in cPanel
- [ ] Dependencies installed
- [ ] .env file configured with correct values
- [ ] SECRET_KEY generated (not default)
- [ ] DEBUG=False
- [ ] ALLOWED_HOSTS set
- [ ] passenger_wsgi.py updated
- [ ] .htaccess updated
- [ ] Static files collected
- [ ] Migrations run
- [ ] Superuser created
- [ ] Application restarted
- [ ] SSL certificate installed
- [ ] Site tested and working

---

**For detailed instructions, see `CPANEL_DEPLOYMENT_GUIDE.md`**
