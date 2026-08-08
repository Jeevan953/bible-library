import os
import sys
import django
import json
import requests

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

def import_gnt_from_stepbible():
    """Import GNT from STEPBible API"""
    
    # Get GNT version
    try:
        gnt_version = BibleVersion.objects.get(abbreviation='GNT')
        print(f"✅ Found GNT version: {gnt_version.name}")
    except BibleVersion.DoesNotExist:
        print("❌ GNT version not found")
        return
    
    # Check if already has verses
    existing = VerseText.objects.filter(bible_version=gnt_version).count()
    if existing > 31100:  # Full Bible has ~31,000 verses
        print(f"✅ GNT already has {existing:,} verses (complete)")
        return
    
    print(f"📊 GNT has {existing:,} verses, importing more...")
    
    # STEPBible API endpoint for GNT
    # You may need to adjust this based on your STEPBible data
    # Try different possible endpoints
    
    # Option 1: Try using the STEPBible data format
    # Check if you have local STEPBible files
    stepbible_file = 'data/GNT.json'
    if os.path.exists(stepbible_file):
        print(f"📁 Found local STEPBible file: {stepbible_file}")
        import_from_file(stepbible_file, gnt_version)
        return
    
    # Option 2: Use the STEPBible TIPNR data format
    tipnr_file = 'data/tipnr/GNT.json'
    if os.path.exists(tipnr_file):
        print(f"📁 Found TIPNR file: {tipnr_file}")
        import_from_file(tipnr_file, gnt_version)
        return
    
    # Option 3: Search for any GNT data file
    import glob
    gnt_files = glob.glob('data/**/*GNT*', recursive=True) + glob.glob('data/**/*gnt*', recursive=True)
    if gnt_files:
        print(f"📁 Found GNT files: {gnt_files}")
        for file in gnt_files:
            if file.endswith('.json'):
                import_from_file(file, gnt_version)
                return
    
    print("❌ No local GNT data found. Please check your data directory.")

def import_from_file(file_path, gnt_version):
    """Import GNT from a local JSON file"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        print(f"📖 Importing from {file_path}...")
        
        total_verses = 0
        new_verses = 0
        
        # Handle different JSON formats
        if 'books' in data:
            # Standard format with 'books' key
            for book_data in data['books']:
                book_name = book_data.get('name')
                if not book_name:
                    continue
                
                book, _ = Book.objects.get_or_create(
                    name=book_name,
                    defaults={'slug': book_name.lower().replace(' ', '_')}
                )
                
                for chapter_data in book_data.get('chapters', []):
                    chapter_num = chapter_data.get('number')
                    if not chapter_num:
                        continue
                    
                    chapter, _ = Chapter.objects.get_or_create(
                        book=book,
                        number=chapter_num
                    )
                    
                    for verse_data in chapter_data.get('verses', []):
                        verse_num = verse_data.get('number')
                        verse_text = verse_data.get('text')
                        
                        if not verse_num or not verse_text:
                            continue
                        
                        verse, _ = Verse.objects.get_or_create(
                            chapter=chapter,
                            number=verse_num
                        )
                        
                        # Check if verse text exists
                        existing_verse = VerseText.objects.filter(
                            bible_version=gnt_version,
                            verse=verse
                        ).first()
                        
                        if not existing_verse:
                            VerseText.objects.create(
                                bible_version=gnt_version,
                                verse=verse,
                                text=verse_text
                            )
                            new_verses += 1
                        total_verses += 1
        
        elif isinstance(data, list):
            # Format where data is a list of verses
            for item in data:
                book_name = item.get('book')
                chapter_num = item.get('chapter')
                verse_num = item.get('verse')
                verse_text = item.get('text')
                
                if not all([book_name, chapter_num, verse_num, verse_text]):
                    continue
                
                book, _ = Book.objects.get_or_create(
                    name=book_name,
                    defaults={'slug': book_name.lower().replace(' ', '_')}
                )
                
                chapter, _ = Chapter.objects.get_or_create(
                    book=book,
                    number=chapter_num
                )
                
                verse, _ = Verse.objects.get_or_create(
                    chapter=chapter,
                    number=verse_num
                )
                
                existing_verse = VerseText.objects.filter(
                    bible_version=gnt_version,
                    verse=verse
                ).first()
                
                if not existing_verse:
                    VerseText.objects.create(
                        bible_version=gnt_version,
                        verse=verse,
                        text=verse_text
                    )
                    new_verses += 1
                total_verses += 1
        
        print(f"✅ Import complete!")
        print(f"  Total verses: {total_verses:,}")
        print(f"  New verses: {new_verses:,}")
        print(f"  Total GNT verses: {VerseText.objects.filter(bible_version=gnt_version).count():,}")
        
    except Exception as e:
        print(f"❌ Error importing from {file_path}: {e}")

if __name__ == "__main__":
    import_gnt_from_stepbible()
