import os
import sys
import django

# Setup Django
sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, Verse, Chapter
from django.db import transaction

# Versions to add
VERSIONS_TO_ADD = [
    ('NIV', 'New International Version', 2011),
    ('ESV', 'English Standard Version', 2016),
    ('NLT', 'New Living Translation', 2015),
    ('CSB', 'Christian Standard Bible', 2017),
    ('NASB', 'New American Standard Bible', 2020),
    ('RSV', 'Revised Standard Version', 1952),
    ('GNT', 'Good News Translation', 1992),
    ('AMP', 'Amplified Bible', 2015),
    ('MSG', 'The Message Bible', 2002),
]

def add_version(abbr, name, year):
    """Add a new Bible version"""
    try:
        # Check if version already exists
        if BibleVersion.objects.filter(abbreviation=abbr).exists():
            print(f"⚠️ {abbr} already exists")
            return False
        
        # Create the version
        version = BibleVersion.objects.create(
            abbreviation=abbr,
            name=name,
            description=f"{name} - Added via script",
            language='English',
            year=year,
            pdf_filename=''  # Empty if not available
        )
        
        print(f"✅ Added {abbr}: {name}")
        return True
        
    except Exception as e:
        print(f"❌ Error adding {abbr}: {e}")
        return False

# Add the versions
print("📖 Adding New Bible Versions")
print("=" * 60)

added = 0
for abbr, name, year in VERSIONS_TO_ADD:
    if add_version(abbr, name, year):
        added += 1

print("\n" + "=" * 60)
print(f"✅ Added {added} new versions. Total: {BibleVersion.objects.count()}")