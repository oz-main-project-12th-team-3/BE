import os
import sys
from pathlib import Path

import django

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest_plugins = ["pytest_django"]

def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
