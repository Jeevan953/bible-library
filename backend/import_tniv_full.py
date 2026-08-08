import os
import sys
import django
import xml.etree.ElementTree as ET

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

# Full book order with positions
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

def get_or_create_book(book_name):
    """Get or create a book with proper position"""
    try:
        return Book.objects.get(name=book_name)
    except Book.DoesNotExist:
        position = BOOK_POSITIONS.get(book_name, 99)
        book = Book.objects.create(
            name=book_name,
            slug=book_name.lower().replace(' ', '_').replace("'", ''),
            position=position
        )
        return book

def import_tniv_full(xml_file, version_abbr):
    """Import complete TNIV Bible"""
    
    # Get the version
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        print(f"✅ Found {version_abbr} version: {version.name}")
    except BibleVersion.DoesNotExist:
        print(f"❌ {version_abbr} version not found")
        print("Creating TNIV version...")
        version = BibleVersion.objects.create(
            abbreviation=version_abbr,
            name="Today's New International Version",
            description="Today's New International Version (TNIV)",
            language='English',
            year=2005,
            pdf_filename=''
        )
        print(f"✅ Created TNIV version")
    
    # Check existing data
    existing = VerseText.objects.filter(bible_version=version).count()
    if existing > 0:
        print(f"⚠️ {version_abbr} already has {existing:,} verses")
        print("Deleting existing data to start fresh...")
        VerseText.objects.filter(bible_version=version).delete()
        print("✅ Deleted existing data")
    
    # Parse XML
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        print(f"📖 Loaded {xml_file}")
    except Exception as e:
        print(f"❌ Error loading XML: {e}")
        return
    
    total_verses = 0
    book_count = 0
    total_books = 0
    
    # Get total books for progress
    for book_elem in root.findall('.//BIBLEBOOK'):
        total_books += 1
    
    print(f"📚 Total books to import: {total_books}\n")
    
    # Process all Bible books
    for book_elem in root.findall('.//BIBLEBOOK'):
        book_name = book_elem.get('bname')
        book_count += 1
        print(f"📖 ({book_count}/{total_books}) Processing {book_name}...")
        
        # Get or create book
        book = get_or_create_book(book_name)
        book_verses = 0
        
        # Process chapters
        for chapter_elem in book_elem.findall('.//CHAPTER'):
            chapter_num = int(chapter_elem.get('cnumber'))
            
            # Get or create chapter
            chapter, _ = Chapter.objects.get_or_create(
                book=book,
                number=chapter_num
            )
            
            # Process verses
            for verse_elem in chapter_elem.findall('.//VERS'):
                verse_num = int(verse_elem.get('vnumber'))
                verse_text = verse_elem.text or ''
                
                # Clean text
                verse_text = ' '.join(verse_text.strip().split())
                
                if not verse_text:
                    continue
                
                # Get or create verse
                verse, _ = Verse.objects.get_or_create(
                    chapter=chapter,
                    number=verse_num
                )
                
                # Create verse text
                VerseText.objects.create(
                    bible_version=version,
                    verse=verse,
                    text=verse_text
                )
                total_verses += 1
                book_verses += 1
                
                if total_verses % 1000 == 0:
                    print(f"  ⏳ Imported {total_verses:,} verses total...")
        
        print(f"  ✅ {book_name}: {book_verses} verses")
    
    print(f"\n🎉 IMPORT COMPLETE!")
    print(f"  📖 Total verses: {total_verses:,}")
    print(f"  📚 Books imported: {book_count}/{total_books}")
    print(f"  ✅ {version_abbr} now has {VerseText.objects.filter(bible_version=version).count():,} verses")

if __name__ == "__main__":
    import_tniv_full('data/TNIV.xml', 'TNIV')
