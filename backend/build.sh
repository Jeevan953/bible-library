#!/bin/bash

echo "🚀 Building Bible Library API..."

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

echo "✅ Build complete!"
