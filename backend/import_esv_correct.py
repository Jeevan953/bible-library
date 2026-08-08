import os
import sys
import django
import json

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

# Book positions
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

def clean_text(text):
    """Clean verse text"""
    if not text:
        return ''
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Remove any weird characters
    return text

def import_esv_correct():
    """Import actual ESV text from JSON file"""
    
    # Get ESV version
    try:
        version = BibleVersion.objects.get(abbreviation='ESV')
        print(f"✅ Found ESV version: {version.name}")
    except BibleVersion.DoesNotExist:
        print("❌ ESV version not found")
        return
    
    # Check if already has data
    existing = VerseText.objects.filter(bible_version=version).count()
    if existing > 30000:
        print(f"✅ ESV already has {existing:,} verses")
        return
    
    # Delete partial data
    if existing > 0:
        print(f"🗑️ Deleting {existing:,} existing verses...")
        VerseText.objects.filter(bible_version=version).delete()
    
    # Load JSON
    print("📖 Loading ESV.json...")
    with open('data/ESV.json', 'r') as f:
        data = json.load(f)
    
    # Get books data
    books_data = data.get('books', {})
    
    verse_texts = []
    total_verses = 0
    
    for book_name, book_data in books_data.items():
        if book_name.startswith('_'):
            continue
        
        print(f"📖 Processing {book_name}...")
        
        # Get or create book
        position = BOOK_POSITIONS.get(book_name, 99)
        try:
            book = Book.objects.get(name=book_name)
        except Book.DoesNotExist:
            book = Book.objects.create(
                name=book_name,
                slug=book_name.lower().replace(' ', '_'),
                position=position
            )
        
        # Process chapters
        if isinstance(book_data, dict):
            for chapter_num, chapter_data in book_data.items():
                try:
                    chapter_num_int = int(chapter_num)
                except (ValueError, TypeError):
                    continue
                
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
                        
                        # Extract text - handle different formats
                        if isinstance(verse_data, str):
                            verse_text = clean_text(verse_data)
                        elif isinstance(verse_data, list):
                            # Extract text from list format
                            text_parts = []
                            for item in verse_data:
                                if isinstance(item, str):
                                    text_parts.append(item)
                                elif isinstance(item, list):
                                    for sub in item:
                                        if isinstance(sub, str):
                                            text_parts.append(sub)
                            verse_text = clean_text(' '.join(text_parts))
                        else:
                            continue
                        
                        if not verse_text:
                            continue
                        
                        verse, _ = Verse.objects.get_or_create(
                            chapter=chapter,
                            number=verse_num_int
                        )
                        
                        verse_texts.append(
                            VerseText(
                                bible_version=version,
                                verse=verse,
                                text=verse_text
                            )
                        )
                        total_verses += 1
    
    # Bulk insert
    print(f"📤 Bulk inserting {total_verses:,} verses...")
    VerseText.objects.bulk_create(verse_texts, batch_size=5000)
    print(f"✅ ESV now has {total_verses:,} verses")

if __name__ == "__main__":
    import_esv_correct()
