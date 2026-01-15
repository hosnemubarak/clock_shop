# Create Admin User Without SSH/Terminal Access

If you don't have SSH/terminal access to your cPanel, here are alternative methods to create a Django superuser.

---

## Method 1: Using Python Script (Recommended)

### Step 1: Edit the Script

1. Open `create_admin.py` in the project root
2. **Change these credentials:**
   ```python
   ADMIN_USERNAME = 'admin'           # Change to your desired username
   ADMIN_EMAIL = 'admin@example.com'  # Change to your email
   ADMIN_PASSWORD = 'ChangeThisPassword123!'  # Change to a strong password
   ```

### Step 2: Run via cPanel Python App

1. **Login to cPanel**
2. **Go to "Setup Python App"**
3. **Click on your application**
4. **Look for "Run Python Script" or "Execute" option**
5. **Select or upload `create_admin.py`**
6. **Run the script**

### Step 3: Security Cleanup

1. **Login to admin panel:** `https://yourdomain.com/admin`
2. **Change your password immediately**
3. **Delete `create_admin.py` from your server**

---

## Method 2: Using Temporary Django View

### Step 1: Edit the View File

1. Open `create_admin_view.py`
2. **Change the credentials at the top:**
   ```python
   ADMIN_USERNAME = 'admin'
   ADMIN_EMAIL = 'admin@example.com'
   ADMIN_PASSWORD = 'ChangeThisPassword123!'
   ```

### Step 2: Add to URLs

1. **Upload `create_admin_view.py` to your project root** (`~/clock_shop/`)

2. **Edit `clock_shop/urls.py`:**
   ```python
   from create_admin_view import create_admin_user
   
   urlpatterns = [
       # ... existing patterns ...
       path('create-admin-temp/', create_admin_user),  # TEMPORARY!
   ]
   ```

3. **Restart your application:**
   - In cPanel: Setup Python App → Restart
   - Or create file: `touch ~/clock_shop/tmp/restart.txt`

### Step 3: Create Admin

1. **Visit:** `https://yourdomain.com/create-admin-temp/`
2. **You'll see a success message with your credentials**

### Step 4: Security Cleanup (CRITICAL!)

1. **Login to admin:** `https://yourdomain.com/admin`
2. **Change your password**
3. **Remove the URL from `urls.py`:**
   ```python
   # DELETE this line:
   path('create-admin-temp/', create_admin_user),
   ```
4. **Delete `create_admin_view.py` from server**
5. **Restart application**

---

## Method 3: Using cPanel File Manager + Database

### Step 1: Generate Password Hash

1. **Create a temporary Python file** `hash_password.py`:
   ```python
   from django.contrib.auth.hashers import make_password
   password = make_password('YourPasswordHere')
   print(password)
   ```

2. **Run it via cPanel Python App** to get the hashed password

### Step 2: Insert via phpMyAdmin/PostgreSQL

1. **Login to cPanel**
2. **Go to phpMyAdmin (MySQL) or PostgreSQL**
3. **Select your database:** `rumaelec_clock_shop_db`
4. **Find table:** `auth_user`
5. **Insert new row:**
   ```sql
   INSERT INTO auth_user (
       username, 
       password, 
       email, 
       is_superuser, 
       is_staff, 
       is_active, 
       date_joined
   ) VALUES (
       'admin',
       'pbkdf2_sha256$...',  -- paste hashed password here
       'admin@example.com',
       1,
       1,
       1,
       NOW()
   );
   ```

---

## Method 4: Using Django Management Command via Web

### Create a Custom Management Command

1. **Create file:** `apps/core/management/commands/createadmin.py`

   ```python
   from django.core.management.base import BaseCommand
   from django.contrib.auth import get_user_model
   
   class Command(BaseCommand):
       help = 'Create admin user'
   
       def handle(self, *args, **options):
           User = get_user_model()
           if not User.objects.filter(username='admin').exists():
               User.objects.create_superuser(
                   username='admin',
                   email='admin@example.com',
                   password='ChangeThisPassword123!'
               )
               self.stdout.write('Admin created!')
           else:
               self.stdout.write('Admin already exists!')
   ```

2. **Run via cPanel Python interface** or create a view that calls:
   ```python
   from django.core.management import call_command
   call_command('createadmin')
   ```

---

## Method 5: Ask Hosting Provider

If none of the above work:

1. **Contact your hosting provider's support**
2. **Ask them to run this command for you:**
   ```bash
   cd ~/clock_shop
   source ~/virtualenv/clock_shop/3.11/bin/activate
   python manage.py createsuperuser
   ```
3. **Provide them with your desired credentials**

---

## Security Best Practices

⚠️ **IMPORTANT:**

1. **Never commit admin credentials to Git**
2. **Always change default passwords immediately**
3. **Delete temporary scripts after use**
4. **Remove temporary URLs from production**
5. **Use strong passwords (12+ characters, mixed case, numbers, symbols)**
6. **Enable two-factor authentication if available**

---

## Recommended Approach

**For cPanel without SSH:**

1. ✅ **Use Method 1 (Python Script)** - Safest and easiest
2. ✅ **Change credentials in the script first**
3. ✅ **Run via cPanel Python App interface**
4. ✅ **Delete script immediately after use**
5. ✅ **Change password via Django admin**

---

## Troubleshooting

### Script doesn't run
- Check Python version matches (3.11)
- Verify virtual environment is activated
- Check file permissions (755 for .py files)

### "Module not found" error
- Ensure you're in the correct directory
- Verify Django is installed: `pip list | grep Django`
- Check DJANGO_SETTINGS_MODULE is correct

### User already exists
- Use Django admin to reset password
- Or use database method to update password hash

---

## After Creating Admin

1. **Login:** `https://yourdomain.com/admin`
2. **Change password immediately**
3. **Create additional users as needed**
4. **Set up proper user permissions**
5. **Remove all temporary files**

---

**Choose the method that works best with your cPanel configuration!**
