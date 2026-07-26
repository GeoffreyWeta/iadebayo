#!/usr/bin/env bash
# Render build script: install, static files, database, demo content.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py seed_demo   # idempotent: skips if content already exists
