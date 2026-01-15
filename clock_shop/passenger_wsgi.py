"""
Passenger WSGI file for cPanel deployment
This file is used by Passenger (cPanel's Python app server) to run the Django application
"""

import sys
import os
from pathlib import Path

# Add the project directory to the sys.path
INTERP = "/home/rumaelec_/virtualenv/clock_shop/3.11/bin/python3"
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Set the project base directory
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clock_shop.settings')

# Import Django WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
