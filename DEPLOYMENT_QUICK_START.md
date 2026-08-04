# Deployment Quick Start Guide

This guide covers deployment for both **cPanel** (Shared Hosting) and **VPS** (Docker).

---

## 🐳 Docker Deployment (VPS)

**Docker is highly recommended for VPS deployments.** It handles all dependencies, database setup, and environment isolation automatically.

### 1. Initial Setup
SSH into your VPS and run:
```bash
# Clone or copy your project files
git clone <your-repo-url> clock_shop
cd clock_shop

# Copy the environment file
cp .env.example .env
nano .env
```

### 2. Configure Environment
Update `.env` with your secure settings:
```env
SECRET_KEY=<generate-new-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
POSTGRES_DB=clock_shop
POSTGRES_USER=clock_shop_user
POSTGRES_PASSWORD=<strong-password>
APP_PORT=80
```

### 3. Deploy
Start the containers in the background:
```bash
docker-compose up -d --build
```

### 4. Setup Database & Admin
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createcachetable
docker-compose exec web python manage.py createsuperuser
```

### 5. Troubleshooting (Docker)
- **View Logs:** `docker-compose logs -f web`
- **Restart App:** `docker-compose restart web`
- **Rebuild Image:** `docker-compose up -d --build web`

---

## 🌐 cPanel Deployment (MySQL)

**Quick reference for deploying Clock Shop on cPanel.**

### 1. Create MySQL Database (cPanel)
```
MySQL Databases → Create Database: clock_shop_db
MySQL Databases → Create User: clock_shop_user (strong password)
MySQL Databases → Add User to Database (ALL PRIVILEGES)
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
- App Root: /home/rumaelec_/clock_shop
- App URL: rumaelectronics.xyz
- Startup: clock_shop/wsgi.py (cPanel will auto-detect)
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

DB_ENGINE=mysql
DB_NAME=rumaelec_clock_shop_db
DB_USER=rumaelec_clock_shop_user
DB_PASSWORD=<your-db-password>
DB_HOST=localhost
DB_PORT=3306
```

**Generate SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

### 6. Configure Environment
```bash
# Create .env file from template
cd ~/clock_shop
cp .env.cpanel .env
nano .env

# Update: SECRET_KEY and DB_PASSWORD
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

# Create cache table
python manage.py createcachetable

# Create admin user
python manage.py createsuperuser
```

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
mysqldump -u rumaelec_clock_shop_user -p rumaelec_clock_shop_db > backup.sql
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
- Test connection: `mysql -u rumaelec_clock_shop_user -p rumaelec_clock_shop_db`
- Verify credentials in .env
- Check MySQL is running: `mysqladmin -u rumaelec_clock_shop_user -p ping`

**Static files missing?**
- Re-run: `python manage.py collectstatic --clear --noinput`
- Check permissions: `chmod -R 755 ~/clock_shop/staticfiles/`

**500 Error?**
- Check logs: `tail -f ~/logs/error_log`
- Temporarily enable DEBUG=True to see detailed errors

---

## 📋 Checklist

- [ ] MySQL database created
- [ ] Database user created with ALL PRIVILEGES
- [ ] Files uploaded to ~/clock_shop
- [ ] Python app configured in cPanel
- [ ] Dependencies installed
- [ ] .env file configured with correct values
- [ ] SECRET_KEY generated (not default)
- [ ] DEBUG=False
- [ ] ALLOWED_HOSTS set
- [ ] Static files collected
- [ ] Migrations run
- [ ] Superuser created
- [ ] Application restarted
- [ ] SSL certificate installed
- [ ] Site tested and working

---

**For detailed instructions, see `CPANEL_DEPLOYMENT_GUIDE.md`**
