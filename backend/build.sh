#!/bin/bash

echo "🚀 Building Bible Library API..."
echo "Python version: $(python --version)"

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

echo "✅ Build complete!"
