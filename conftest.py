import os
import sys
from pathlib import Path

import django

# Add the project root to the Python path to ensure all apps are discoverable.
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

pytest_plugins = ["pytest_django"]

def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
