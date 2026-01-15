# cPanel Deployment Guide for Clock Shop

This guide will help you deploy the Clock Shop Django application on cPanel with PostgreSQL database.

---

## Prerequisites

- cPanel account with Python support (Python 3.9+)
- SSH access to your cPanel account
- MySQL database access
- Domain or subdomain configured

---

## Step 1: Create PostgreSQL Database

1. **Login to cPanel**
2. **Go to PostgreSQL® Databases**
3. **Create a new database:**
   - Database name: `clock_shop_db` (cPanel will prefix it with your username)
   - Note the full database name (e.g., `rumaelec_clock_shop_db`)

4. **Create a database user:**
   - Username: `clock_shop_user`
   - Password: Generate a strong password
   - Note the full username (e.g., `rumaelec_clock_shop_user`)

5. **Add user to database:**
   - Select the user and database
   - Grant **ALL PRIVILEGES**

6. **Note your credentials:**
   ```
   DB_NAME: rumaelec_clock_shop_db
   DB_USER: rumaelec_clock_shop_user
   DB_PASSWORD: your_generated_password
   DB_HOST: localhost
   DB_PORT: 5432
   ```

---

## Step 2: Upload Project Files

### Option A: Using File Manager (Easier)

1. **Compress your project locally:**
   
   **Windows (PowerShell):**
   ```powershell
   # On your local machine
   cd clock_shop\clock_shop
   Get-ChildItem -Recurse -File | Where-Object {
       $_.FullName -notmatch "\\.git\\" -and
       $_.FullName -notmatch "__pycache__" -and
       $_.Extension -ne ".pyc" -and
       $_.Name -ne "db.sqlite3" -and
       $_.FullName -notmatch "\\.venv\\"
   } | Compress-Archive -DestinationPath clock_shop.zip -Force
   ```
   
   **Linux/Mac:**
   ```bash
   # On your local machine
   cd clock_shop
   zip -r clock_shop.zip . -x "*.git*" -x "*__pycache__*" -x "*.pyc" -x "db.sqlite3" -x ".venv/*"
   ```

2. **Upload via cPanel File Manager:**
   - Go to **File Manager** in cPanel
   - Navigate to your home directory or public_html
   - Create a folder: `clock_shop`
   - Upload `clock_shop.zip`
   - Extract the archive
   - Delete the zip file

### Option B: Using Git (Recommended)

1. **SSH into your cPanel:**
   ```bash
   ssh username@yourdomain.com
   ```

2. **Clone your repository:**
   ```bash
   cd ~
   git clone https://github.com/yourusername/clock_shop.git
   # OR upload via SFTP
   ```

---

## Step 3: Setup Python Virtual Environment

1. **Login to cPanel**
2. **Go to "Setup Python App"**
3. **Create Application:**
   - Python version: **3.11** (or latest available)
   - Application root: `/home/username/clock_shop`
   - Application URL: Your domain or subdomain
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`

4. **Click "Create"**

5. **Note the virtual environment path:**
   ```
   /home/username/virtualenv/clock_shop/3.11
   ```

---

## Step 4: Install Dependencies

1. **Access terminal (SSH or cPanel Terminal)**

2. **Activate virtual environment:**
   ```bash
   source ~/virtualenv/clock_shop/3.11/bin/activate
   ```

3. **Navigate to project:**
   ```bash
   cd ~/clock_shop
   ```

4. **Install requirements:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   **Note:** If `mysqlclient` installation fails, you may need to install system dependencies:
   ```bash
   # Contact your hosting provider if this doesn't work
   pip install mysqlclient
   ```

---

## Step 5: Configure Environment Variables

1. **Create `.env` file in project root:**
   ```bash
   cd ~/clock_shop
   nano .env
   ```

2. **Add the following configuration:**
   ```env
   # Security Settings
   SECRET_KEY=your-very-long-random-secret-key-generate-new-one
   DEBUG=False
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
   
   # Database Settings (PostgreSQL)
   DB_ENGINE=postgresql
   DB_NAME=rumaelec_clock_shop_db
   DB_USER=rumaelec_clock_shop_user
   DB_PASSWORD=your_database_password
   DB_HOST=localhost
   DB_PORT=5432
   
   # Business Settings
   SHOP_NAME=Clock Shop
   CURRENCY_SYMBOL=৳
   LOW_STOCK_THRESHOLD=5
   ```

3. **Generate SECRET_KEY:**
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
   Copy the output and paste it as your SECRET_KEY

4. **Save and exit** (Ctrl+X, then Y, then Enter)

---

## Step 6: Update Configuration Files

1. **Update `passenger_wsgi.py`:**
   ```bash
   nano ~/clock_shop/passenger_wsgi.py
   ```
   
   Replace `YOUR_CPANEL_USERNAME` with your actual cPanel username:
   ```python
   INTERP = os.path.expanduser("~/virtualenv/clock_shop/3.11/bin/python3")
   ```

2. **Update `.htaccess`:**
   ```bash
   nano ~/clock_shop/.htaccess
   ```
   
   Replace `YOUR_CPANEL_USERNAME` with your actual username in both places.

---

## Step 7: Collect Static Files

1. **Run collectstatic:**
   ```bash
   cd ~/clock_shop
   source ~/virtualenv/clock_shop/3.11/bin/activate
   python manage.py collectstatic --noinput
   ```

---

## Step 8: Run Database Migrations

1. **Create database tables:**
   ```bash
   python manage.py migrate
   ```

2. **Create superuser:**
   
   **If you have SSH access:**
   ```bash
   python manage.py createsuperuser
   ```
   Follow the prompts to create your admin account.
   
   **If you DON'T have SSH access:**
   See `CREATE_ADMIN_WITHOUT_SSH.md` for alternative methods:
   - Method 1: Use `create_admin.py` script (recommended)
   - Method 2: Use temporary Django view
   - Method 3: Direct database insertion
   - Method 4: Contact hosting provider

3. **Load initial data (optional):**
   ```bash
   # If you have fixtures
   python manage.py loaddata fixtures/initial_data.json
   ```

---

## Step 9: Configure Static Files in cPanel

### Option A: Serve from Django (Easier)

Django will serve static files using WhiteNoise. No additional configuration needed.

### Option B: Serve via Apache (Better Performance)

1. **In cPanel File Manager:**
   - Create a symbolic link from `public_html/static` to `~/clock_shop/staticfiles`
   - Create a symbolic link from `public_html/media` to `~/clock_shop/media`

2. **Or via SSH:**
   ```bash
   ln -s ~/clock_shop/staticfiles ~/public_html/static
   ln -s ~/clock_shop/media ~/public_html/media
   ```

---

## Step 10: Restart Application

1. **In cPanel "Setup Python App":**
   - Click on your application
   - Click **"Restart"** button

2. **Or create/touch restart file:**
   ```bash
   touch ~/clock_shop/tmp/restart.txt
   ```

---

## Step 11: Test Your Application

1. **Visit your domain:**
   ```
   https://yourdomain.com
   ```

2. **Login to admin:**
   ```
   https://yourdomain.com/admin
   ```

3. **Check for errors:**
   - If you see errors, check logs in cPanel or via SSH:
   ```bash
   tail -f ~/clock_shop/logs/error.log
   ```

---

## Troubleshooting

### Application doesn't start

1. **Check Python version:**
   ```bash
   python --version
   ```

2. **Check virtual environment activation:**
   ```bash
   which python
   # Should show: /home/username/virtualenv/clock_shop/3.11/bin/python
   ```

3. **Check passenger_wsgi.py path:**
   ```bash
   cat ~/clock_shop/passenger_wsgi.py
   ```

### Database connection errors

1. **Verify database credentials:**
   ```bash
   cat ~/clock_shop/.env | grep DB_
   ```

2. **Test PostgreSQL connection:**
   ```bash
   psql -U rumaelec_clock_shop_user -d rumaelec_clock_shop_db -h localhost
   ```

3. **Check PostgreSQL is running:**
   ```bash
   pg_isready -h localhost
   ```

### Static files not loading

1. **Check STATIC_ROOT:**
   ```bash
   ls -la ~/clock_shop/staticfiles/
   ```

2. **Re-run collectstatic:**
   ```bash
   python manage.py collectstatic --clear --noinput
   ```

3. **Check file permissions:**
   ```bash
   chmod -R 755 ~/clock_shop/staticfiles/
   chmod -R 755 ~/clock_shop/media/
   ```

### 500 Internal Server Error

1. **Enable DEBUG temporarily:**
   ```bash
   nano ~/clock_shop/.env
   # Set DEBUG=True
   ```

2. **Check error logs:**
   ```bash
   tail -f ~/logs/error_log
   ```

3. **Check Django logs:**
   ```bash
   python manage.py check --deploy
   ```

### psycopg2 installation fails

1. **Try installing with pip:**
   ```bash
   pip install psycopg2-binary
   ```

2. **If that fails, contact your hosting provider** - they may need to install PostgreSQL development headers

3. **Check PostgreSQL client libraries:**
   ```bash
   which pg_config
   ```

---

## Updating Your Application

1. **Upload new code:**
   ```bash
   cd ~/clock_shop
   git pull origin main
   # OR upload via File Manager/SFTP
   ```

2. **Activate virtual environment:**
   ```bash
   source ~/virtualenv/clock_shop/3.11/bin/activate
   ```

3. **Install new dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Collect static files:**
   ```bash
   python manage.py collectstatic --noinput
   ```

6. **Restart application:**
   ```bash
   touch ~/clock_shop/tmp/restart.txt
   ```

---

## Security Checklist

- [ ] `DEBUG=False` in production
- [ ] Strong `SECRET_KEY` generated
- [ ] `ALLOWED_HOSTS` configured correctly
- [ ] `CSRF_TRUSTED_ORIGINS` set for your domain
- [ ] Database user has strong password
- [ ] SSL certificate installed (HTTPS)
- [ ] File permissions set correctly (755 for directories, 644 for files)
- [ ] `.env` file is not publicly accessible
- [ ] Regular backups configured

---

## Backup Strategy

### Database Backup

1. **Via cPanel:**
   - Go to **Backup** → **Download a PostgreSQL Database Backup**

2. **Via SSH:**
   ```bash
   pg_dump -U rumaelec_clock_shop_user -h localhost rumaelec_clock_shop_db > backup_$(date +%Y%m%d).sql
   ```

### Files Backup

1. **Via cPanel:**
   - Go to **Backup** → **Download a Home Directory Backup**

2. **Via SSH:**
   ```bash
   tar -czf clock_shop_backup_$(date +%Y%m%d).tar.gz ~/clock_shop
   ```

---

## Performance Optimization

1. **Enable caching in settings.py:**
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
           'LOCATION': 'cache_table',
       }
   }
   ```
   Then run: `python manage.py createcachetable`

2. **Use CDN for static files** (optional)

3. **Enable Gzip compression** (already configured in .htaccess)

4. **Optimize database queries** (use select_related, prefetch_related)

---

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review Django logs
3. Contact your hosting provider for server-specific issues
4. Check Django documentation: https://docs.djangoproject.com/

---

## Additional Resources

- Django Deployment Checklist: https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/
- cPanel Documentation: https://docs.cpanel.net/
- MySQL Documentation: https://dev.mysql.com/doc/

---

**Congratulations! Your Clock Shop application should now be running on cPanel with MySQL!** 🎉
