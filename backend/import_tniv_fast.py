import os
import sys
import django
import xml.etree.ElementTree as ET

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

def import_tniv_fast(xml_file, version_abbr):
    """Fast import TNIV using bulk_create"""
    
    # Get version
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        print(f"✅ Found {version_abbr}")
    except BibleVersion.DoesNotExist:
        print(f"❌ {version_abbr} not found")
        return
    
    # Check if already has data
    existing = VerseText.objects.filter(bible_version=version).count()
    if existing > 30000:
        print(f"✅ {version_abbr} already has {existing:,} verses")
        return
    
    if existing > 0:
        print(f"🗑️ Deleting {existing:,} existing verses...")
        VerseText.objects.filter(bible_version=version).delete()
    
    # Parse XML
    print("📖 Parsing XML...")
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Collect all verse texts for bulk insert
    verse_texts = []
    book_count = 0
    total_books = len(root.findall('.//BIBLEBOOK'))
    
    for book_elem in root.findall('.//BIBLEBOOK'):
        book_name = book_elem.get('bname')
        book_count += 1
        print(f"📖 ({book_count}/{total_books}) Processing {book_name}...")
        
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
        for chapter_elem in book_elem.findall('.//CHAPTER'):
            chapter_num = int(chapter_elem.get('cnumber'))
            chapter, _ = Chapter.objects.get_or_create(book=book, number=chapter_num)
            
            # Process verses
            for verse_elem in chapter_elem.findall('.//VERS'):
                verse_num = int(verse_elem.get('vnumber'))
                verse_text = ' '.join((verse_elem.text or '').strip().split())
                
                if not verse_text:
                    continue
                
                # Get or create verse
                verse, _ = Verse.objects.get_or_create(chapter=chapter, number=verse_num)
                
                # Add to bulk list
                verse_texts.append(
                    VerseText(
                        bible_version=version,
                        verse=verse,
                        text=verse_text
                    )
                )
        
        print(f"  ✅ {book_name}: {len(verse_texts)} verses so far")
    
    # Bulk insert all at once
    print(f"\n📤 Bulk inserting {len(verse_texts):,} verses...")
    VerseText.objects.bulk_create(verse_texts, batch_size=5000)
    print(f"✅ Import complete! TNIV now has {len(verse_texts):,} verses")

if __name__ == "__main__":
    import_tniv_fast('data/TNIV.xml', 'TNIV')
