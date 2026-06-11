"""
Pytest configuration — ensure Django is set up before any test imports.
"""

import os


def pytest_configure():
    """Called before test collection — set up Django once."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    import django
    django.setup()
