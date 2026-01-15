#!/usr/bin/env python
"""
Create Admin User Script for cPanel Deployment
Run this script via cPanel Python App or File Manager to create a superuser
without terminal access.

Usage:
1. Upload this file to your project root (~/clock_shop/)
2. In cPanel, go to "Setup Python App"
3. Click "Run Python Script" or use the web interface
4. Or create a temporary view to run this

After creating the admin, DELETE this file for security!
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clock_shop.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Admin user credentials - CHANGE THESE!
ADMIN_USERNAME = 'admin'
ADMIN_EMAIL = 'admin@example.com'
ADMIN_PASSWORD = 'ChangeThisPassword123!'  # IMPORTANT: Change this!

def create_admin():
    """Create superuser if it doesn't exist."""
    if User.objects.filter(username=ADMIN_USERNAME).exists():
        print(f"✗ User '{ADMIN_USERNAME}' already exists!")
        print(f"  If you need to reset the password, use Django admin or shell.")
        return False
    
    try:
        user = User.objects.create_superuser(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD
        )
        print(f"✓ Superuser created successfully!")
        print(f"  Username: {ADMIN_USERNAME}")
        print(f"  Email: {ADMIN_EMAIL}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print(f"\n⚠ IMPORTANT: Change the password after first login!")
        print(f"⚠ DELETE this file (create_admin.py) for security!")
        return True
    except Exception as e:
        print(f"✗ Error creating superuser: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Creating Django Superuser")
    print("=" * 60)
    create_admin()
    print("=" * 60)
