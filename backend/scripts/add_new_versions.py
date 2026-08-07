import os
import sys
import django

# Setup Django
sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book
from django.db import transaction
import requests
import json
from datetime import datetime

# Versions to add (you can expand this)
VERSIONS_TO_ADD = [
    {'abbr': 'NIV', 'name': 'New International Version', 'year': 2011},
    {'abbr': 'ESV', 'name': 'English Standard Version', 'year': 2016},
    {'abbr': 'NLT', 'name': 'New Living Translation', 'year': 2015},
    {'abbr': 'CSB', 'name': 'Christian Standard Bible', 'year': 2017},
    {'abbr': 'NASB', 'name': 'New American Standard Bible', 'year': 2020},
    {'abbr': 'RSV', 'name': 'Revised Standard Version', 'year': 1952},
    {'abbr': 'GNT', 'name': 'Good News Translation', 'year': 1992},
    {'abbr': 'AMP', 'name': 'Amplified Bible', 'year': 2015},
    {'abbr': 'MSG', 'name': 'The Message Bible', 'year': 2002},
    {'abbr': 'TLB', 'name': 'The Living Bible', 'year': 1971},
    {'abbr': 'NET', 'name': 'New English Translation', 'year': 2017},
    {'abbr': 'LSV', 'name': 'Literal Standard Version', 'year': 2020},
]

def add_bible_version(abbr, name, year):
    """Add a new Bible version to the database"""
    try:
        # Check if version already exists
        if BibleVersion.objects.filter(abbreviation=abbr).exists():
            print(f"⚠️ {abbr} already exists")
            return False
        
        # Create the version
        version = BibleVersion.objects.create(
            abbreviation=abbr,
            name=name,
            description=f"{name}",
            language='English',
            year=year,
            pdf_filename=''
        )
        print(f"✅ Added {abbr}: {name}")
        return version
        
    except Exception as e:
        print(f"❌ Error adding {abbr}: {e}")
        return None

def import_verses_from_bible_api(version_abbr):
    """Import verses from bible-api.com"""
    try:
        # First, get the version object
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        
        # Check if verses already exist
        if VerseText.objects.filter(bible_version=version).exists():
            print(f"  ℹ️ {version_abbr} already has verses")
            return True
        
        # API endpoint - using KJV as source since many versions aren't available
        # You can also use: https://api.bible/ (requires API key)
        api_url = f"https://bible-api.com/genesis/1?translation={version_abbr.lower()}"
        
        print(f"  ⏳ Fetching from {api_url}...")
        response = requests.get(api_url, timeout=30)
        
        if response.status_code != 200:
            print(f"  ❌ API returned status {response.status_code}")
            return False
        
        data = response.json()
        
        # Get or create the book
        book_name = data.get('book', 'Genesis')
        book, _ = Book.objects.get_or_create(
            name=book_name,
            defaults={'slug': book_name.lower(), 'position': 1}
        )
        
        # Get or create chapter
        chapter_num = data.get('chapter', 1)
        chapter, _ = Chapter.objects.get_or_create(
            book=book,
            number=chapter_num
        )
        
        # Add verses
        verses_added = 0
        verses_data = data.get('verses', {})
        
        for verse_num, verse_text in verses_data.items():
            # Get or create the Verse entry
            verse, _ = Verse.objects.get_or_create(
                chapter=chapter,
                number=int(verse_num)
            )
            
            # Create the VerseText linking version to verse
            VerseText.objects.create(
                bible_version=version,
                verse=verse,
                text=verse_text
            )
            verses_added += 1
        
        print(f"  ✅ Added {verses_added} verses to {version_abbr}")
        return True
        
    except BibleVersion.DoesNotExist:
        print(f"  ❌ Version {version_abbr} not found in database")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def copy_verses_from_existing_version(source_abbr, target_abbr):
    """Copy verses from an existing version to a new version"""
    try:
        source = BibleVersion.objects.get(abbreviation=source_abbr)
        target = BibleVersion.objects.get(abbreviation=target_abbr)
        
        # Check if target already has verses
        if VerseText.objects.filter(bible_version=target).exists():
            print(f"  ℹ️ {target_abbr} already has verses")
            return True
        
        # Get all verse texts from source
        source_verse_texts = VerseText.objects.filter(bible_version=source)
        count = 0
        
        for source_text in source_verse_texts:
            # Create new verse text for target
            VerseText.objects.create(
                bible_version=target,
                verse=source_text.verse,
                text=source_text.text  # Same text, just linked to new version
            )
            count += 1
            
            # Progress update
            if count % 1000 == 0:
                print(f"  📊 Copied {count} verses...")
        
        print(f"  ✅ Copied {count} verses from {source_abbr} to {target_abbr}")
        return True
        
    except BibleVersion.DoesNotExist as e:
        print(f"  ❌ Version not found: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def import_from_file(version_abbr, file_path):
    """Import verses from a JSON file"""
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        count = 0
        for book_data in data.get('books', []):
            book, _ = Book.objects.get_or_create(
                name=book_data['name'],
                defaults={'slug': book_data['name'].lower(), 'position': book_data.get('position', 1)}
            )
            
            for chapter_data in book_data.get('chapters', []):
                chapter, _ = Chapter.objects.get_or_create(
                    book=book,
                    number=chapter_data['number']
                )
                
                for verse_data in chapter_data.get('verses', []):
                    verse, _ = Verse.objects.get_or_create(
                        chapter=chapter,
                        number=verse_data['number']
                    )
                    
                    VerseText.objects.create(
                        bible_version=version,
                        verse=verse,
                        text=verse_data['text']
                    )
                    count += 1
        
        print(f"  ✅ Imported {count} verses from {file_path}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    print("📖 Bible Version Manager")
    print("=" * 60)
    
    # Step 1: Add versions to the database
    print("\n📌 Adding new versions...")
    added_versions = []
    
    for v in VERSIONS_TO_ADD:
        version = add_bible_version(v['abbr'], v['name'], v['year'])
        if version:
            added_versions.append(v['abbr'])
    
    if not added_versions:
        print("\n⚠️ No new versions added. Check if they already exist.")
        return
    
    # Step 2: Choose how to add verses
    print("\n📌 Adding verses...")
    print("Options:")
    print("  1. Copy from existing version (fastest)")
    print("  2. Import from API (may not have all versions)")
    print("  3. Import from file")
    
    # For now, let's copy from KJV if available
    if BibleVersion.objects.filter(abbreviation='KJV').exists():
        print(f"\n📋 Copying verses from KJV to new versions...")
        for abbr in added_versions:
            print(f"\n⏳ Processing {abbr}...")
            copy_verses_from_existing_version('KJV', abbr)
    else:
        print("\n⚠️ KJV not found. Trying API import...")
        for abbr in added_versions:
            print(f"\n⏳ Processing {abbr}...")
            import_verses_from_bible_api(abbr)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    total_versions = BibleVersion.objects.count()
    total_verses = VerseText.objects.count()
    print(f"  Total Bible Versions: {total_versions}")
    print(f"  Total Verse Texts: {total_verses}")
    
    # Show what was added
    print("\n  New versions added:")
    for abbr in added_versions:
        version = BibleVersion.objects.get(abbreviation=abbr)
        verse_count = VerseText.objects.filter(bible_version=version).count()
        print(f"    - {abbr}: {version.name} ({verse_count:,} verses)")

if __name__ == "__main__":
    main()