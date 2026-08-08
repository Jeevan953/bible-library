import os
import sys
import django
import json
import re

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

def extract_text_from_esv_data(verse_data):
    """Extract plain text from ESV's complex nested structure"""
    if isinstance(verse_data, str):
        return verse_data
    elif isinstance(verse_data, list):
        # Handle list format with Strong's numbers
        text_parts = []
        for item in verse_data:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, list):
                # Handle nested lists like ["word", "G1234"]
                if item and isinstance(item[0], str):
                    text_parts.append(item[0])
                else:
                    # Recursively process nested lists
                    for sub_item in item:
                        if isinstance(sub_item, str):
                            text_parts.append(sub_item)
                        elif isinstance(sub_item, list) and sub_item:
                            if isinstance(sub_item[0], str):
                                text_parts.append(sub_item[0])
        return ' '.join(text_parts).strip()
    elif isinstance(verse_data, dict):
        # If it's a dictionary, try to find text
        if 'text' in verse_data:
            return verse_data['text']
        elif 'content' in verse_data:
            return verse_data['content']
        else:
            # Try to extract from any string values
            for value in verse_data.values():
                if isinstance(value, str):
                    return value
    return str(verse_data)

def import_esv_from_json(file_path, version_abbr):
    """Import ESV from JSON file"""
    
    # Get the version
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        print(f"✅ Found {version_abbr} version: {version.name}")
    except BibleVersion.DoesNotExist:
        print(f"❌ {version_abbr} version not found")
        return
    
    # Check if already has complete data
    existing = VerseText.objects.filter(bible_version=version).count()
    if existing > 30000:
        print(f"✅ {version_abbr} already has {existing:,} verses (complete)")
        return
    
    # Load the JSON file
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"📖 Loaded {file_path}")
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return
    
    total_verses = 0
    new_verses = 0
    skipped_verses = 0
    
    # The ESV.json might be a dictionary with book names as keys
    if isinstance(data, dict):
        # Check if there's a 'books' key
        if 'books' in data:
            books_data = data['books']
        else:
            books_data = data
        
        for book_name, book_data in books_data.items():
            print(f"📖 Processing {book_name}...")
            
            # Skip if book_name is not a string or is a metadata key
            if not isinstance(book_name, str) or book_name.startswith('_'):
                continue
            
            # Get or create book
            book, _ = Book.objects.get_or_create(
                name=book_name,
                defaults={'slug': book_name.lower().replace(' ', '_').replace("'", '')}
            )
            
            # Handle different chapter formats
            if isinstance(book_data, dict):
                for chapter_num, chapter_data in book_data.items():
                    # Skip if chapter_num is not a number
                    try:
                        chapter_num_int = int(chapter_num)
                    except (ValueError, TypeError):
                        continue
                    
                    # Get or create chapter
                    chapter, _ = Chapter.objects.get_or_create(
                        book=book,
                        number=chapter_num_int
                    )
                    
                    # Process verses
                    if isinstance(chapter_data, dict):
                        for verse_num, verse_data in chapter_data.items():
                            try:
                                verse_num_int = int(verse_num)
                            except (ValueError, TypeError):
                                continue
                            
                            # Extract text
                            verse_text = extract_text_from_esv_data(verse_data)
                            
                            # Skip if text is empty or too short
                            if not verse_text or len(verse_text.strip()) < 3:
                                skipped_verses += 1
                                continue
                            
                            # Get or create verse
                            verse, _ = Verse.objects.get_or_create(
                                chapter=chapter,
                                number=verse_num_int
                            )
                            
                            # Check if verse text exists
                            existing_verse = VerseText.objects.filter(
                                bible_version=version,
                                verse=verse
                            ).first()
                            
                            if existing_verse:
                                # Update text if different
                                if existing_verse.text != verse_text:
                                    existing_verse.text = verse_text
                                    existing_verse.save()
                                    new_verses += 1
                            else:
                                VerseText.objects.create(
                                    bible_version=version,
                                    verse=verse,
                                    text=verse_text
                                )
                                new_verses += 1
                            total_verses += 1
                            
                            if total_verses % 1000 == 0:
                                print(f"  Processed {total_verses:,} verses...")
    
    elif isinstance(data, list):
        # Handle list format
        for item in data:
            book_name = item.get('book') or item.get('book_name')
            chapter_num = item.get('chapter') or item.get('chapter_num')
            verse_num = item.get('verse') or item.get('verse_num')
            verse_text = item.get('text') or item.get('verse_text')
            
            if not all([book_name, chapter_num, verse_num, verse_text]):
                continue
            
            # Get or create book
            book, _ = Book.objects.get_or_create(
                name=book_name,
                defaults={'slug': book_name.lower().replace(' ', '_')}
            )
            
            # Get or create chapter
            chapter, _ = Chapter.objects.get_or_create(
                book=book,
                number=int(chapter_num)
            )
            
            # Get or create verse
            verse, _ = Verse.objects.get_or_create(
                chapter=chapter,
                number=int(verse_num)
            )
            
            # Check if verse text exists
            existing_verse = VerseText.objects.filter(
                bible_version=version,
                verse=verse
            ).first()
            
            if not existing_verse:
                VerseText.objects.create(
                    bible_version=version,
                    verse=verse,
                    text=verse_text
                )
                new_verses += 1
            total_verses += 1
    
    print(f"\n✅ Import complete!")
    print(f"  Total verses processed: {total_verses:,}")
    print(f"  New/updated verses: {new_verses:,}")
    print(f"  Skipped verses (empty/too short): {skipped_verses:,}")
    print(f"  Total {version_abbr} verses: {VerseText.objects.filter(bible_version=version).count():,}")

if __name__ == "__main__":
    import_esv_from_json('data/ESV.json', 'ESV')
