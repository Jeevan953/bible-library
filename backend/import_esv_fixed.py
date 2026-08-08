import os
import sys
import django
import json
import re

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

# Bible book order with positions
BOOK_POSITIONS = {
    "Genesis": 1, "Exodus": 2, "Leviticus": 3, "Numbers": 4, "Deuteronomy": 5,
    "Joshua": 6, "Judges": 7, "Ruth": 8, "1 Samuel": 9, "2 Samuel": 10,
    "1 Kings": 11, "2 Kings": 12, "1 Chronicles": 13, "2 Chronicles": 14, "Ezra": 15,
    "Nehemiah": 16, "Esther": 17, "Job": 18, "Psalms": 19, "Proverbs": 20,
    "Ecclesiastes": 21, "Song of Solomon": 22, "Isaiah": 23, "Jeremiah": 24, "Lamentations": 25,
    "Ezekiel": 26, "Daniel": 27, "Hosea": 28, "Joel": 29, "Amos": 30,
    "Obadiah": 31, "Jonah": 32, "Micah": 33, "Nahum": 34, "Habakkuk": 35,
    "Zephaniah": 36, "Haggai": 37, "Zechariah": 38, "Malachi": 39,
    "Matthew": 40, "Mark": 41, "Luke": 42, "John": 43, "Acts": 44,
    "Romans": 45, "1 Corinthians": 46, "2 Corinthians": 47, "Galatians": 48, "Ephesians": 49,
    "Philippians": 50, "Colossians": 51, "1 Thessalonians": 52, "2 Thessalonians": 53,
    "1 Timothy": 54, "2 Timothy": 55, "Titus": 56, "Philemon": 57, "Hebrews": 58,
    "James": 59, "1 Peter": 60, "2 Peter": 61, "1 John": 62, "2 John": 63,
    "3 John": 64, "Jude": 65, "Revelation": 66
}

# Map of book name variations
BOOK_NAME_MAP = {
    "Song of Solomon": "Song of Solomon",
    "Song of Songs": "Song of Solomon",
    "I Samuel": "1 Samuel",
    "II Samuel": "2 Samuel",
    "I Kings": "1 Kings",
    "II Kings": "2 Kings",
    "I Chronicles": "1 Chronicles",
    "II Chronicles": "2 Chronicles",
    "I Corinthians": "1 Corinthians",
    "II Corinthians": "2 Corinthians",
    "I Thessalonians": "1 Thessalonians",
    "II Thessalonians": "2 Thessalonians",
    "I Timothy": "1 Timothy",
    "II Timothy": "2 Timothy",
    "I Peter": "1 Peter",
    "II Peter": "2 Peter",
    "I John": "1 John",
    "II John": "2 John",
    "III John": "3 John",
}

def get_book_position(book_name):
    """Get the position for a book name"""
    # Normalize the book name
    normalized = BOOK_NAME_MAP.get(book_name, book_name)
    return BOOK_POSITIONS.get(normalized, 99)

def extract_text_from_esv_data(verse_data):
    """Extract plain text from ESV's complex nested structure"""
    if isinstance(verse_data, str):
        return verse_data
    elif isinstance(verse_data, list):
        text_parts = []
        for item in verse_data:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, list):
                for sub_item in item:
                    if isinstance(sub_item, str):
                        text_parts.append(sub_item)
                    elif isinstance(sub_item, list):
                        for sub_sub in sub_item:
                            if isinstance(sub_sub, str):
                                text_parts.append(sub_sub)
        return ' '.join(text_parts).strip()
    elif isinstance(verse_data, dict):
        if 'text' in verse_data:
            return verse_data['text']
        elif 'content' in verse_data:
            return verse_data['content']
        # Try to extract text from any string values
        for key, value in verse_data.items():
            if isinstance(value, str) and len(value) > 10:
                return value
    return ''

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
    
    # Get books data
    if 'books' in data:
        books_data = data['books']
    else:
        books_data = data
    
    total_verses = 0
    new_verses = 0
    skipped_verses = 0
    
    for book_name, book_data in books_data.items():
        # Skip metadata keys
        if book_name.startswith('_') or book_name in ['version', 'versionName', 'meta']:
            continue
        
        # Normalize book name
        normalized_name = BOOK_NAME_MAP.get(book_name, book_name)
        print(f"📖 Processing {book_name} -> {normalized_name}...")
        
        # Get or create book with position
        try:
            book = Book.objects.get(name=normalized_name)
            print(f"  ✅ Found existing book: {normalized_name}")
        except Book.DoesNotExist:
            position = get_book_position(normalized_name)
            book = Book.objects.create(
                name=normalized_name,
                slug=normalized_name.lower().replace(' ', '_').replace("'", ''),
                position=position
            )
            print(f"  ✅ Created book: {normalized_name} (position: {position})")
        
        # Process chapters
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
                        
                        # Clean up text (remove extra spaces)
                        verse_text = ' '.join(verse_text.split())
                        
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
    
    print(f"\n✅ Import complete!")
    print(f"  Total verses processed: {total_verses:,}")
    print(f"  New/updated verses: {new_verses:,}")
    print(f"  Skipped verses: {skipped_verses:,}")
    print(f"  Total {version_abbr} verses: {VerseText.objects.filter(bible_version=version).count():,}")

if __name__ == "__main__":
    import_esv_from_json('data/ESV.json', 'ESV')
