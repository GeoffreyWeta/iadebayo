"""
cPanel "Setup Python App" entry point (Phusion Passenger).

cPanel looks for `application` in this file. Point the app root at this
project folder and Passenger does the rest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402,F401
