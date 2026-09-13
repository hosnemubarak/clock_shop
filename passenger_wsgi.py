import os
import sys

# Paths
PROJECT_PATH = "/home/rumaelec/clock_shop"
VENV_PATH = "/home/rumaelec/virtualenv/clock_shop/3.11"

# Add project & site-packages
sys.path.insert(0, PROJECT_PATH)
sys.path.insert(0, os.path.join(VENV_PATH, "lib/python3.11/site-packages"))

# Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clock_shop.settings")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Setup Django
import django
django.setup()

# REQUIRED by Passenger
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
