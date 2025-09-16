import os

import django

pytest_plugins = ["pytest_django"]

def pytest_configure():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
