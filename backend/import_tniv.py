import os
import sys
import django
import xml.etree.ElementTree as ET
import json

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

# Book name mapping
BOOK_NAMES = {
    'GEN': 'Genesis', 'EXO': 'Exodus', 'LEV': 'Leviticus', 'NUM': 'Numbers', 
    'DEU': 'Deuteronomy', 'JOS': 'Joshua', 'JDG': 'Judges', 'RUT': 'Ruth',
    '1SA': '1 Samuel', '2SA': '2 Samuel', '1KI': '1 Kings', '2KI': '2 Kings',
    '1CH': '1 Chronicles', '2CH': '2 Chronicles', 'EZR': 'Ezra', 'NEH': 'Nehemiah',
    'EST': 'Esther', 'JOB': 'Job', 'PSA': 'Psalms', 'PRO': 'Proverbs',
    'ECC': 'Ecclesiastes', 'SNG': 'Song of Solomon', 'ISA': 'Isaiah', 'JER': 'Jeremiah',
    'LAM': 'Lamentations', 'EZK': 'Ezekiel', 'DAN': 'Daniel', 'HOS': 'Hosea',
    'JOL': 'Joel', 'AMO': 'Amos', 'OBA': 'Obadiah', 'JON': 'Jonah',
    'MIC': 'Micah', 'NAM': 'Nahum', 'HAB': 'Habakkuk', 'ZEP': 'Zephaniah',
    'HAG': 'Haggai', 'ZEC': 'Zechariah', 'MAL': 'Malachi',
    'MAT': 'Matthew', 'MRK': 'Mark', 'LUK': 'Luke', 'JHN': 'John',
    'ACT': 'Acts', 'ROM': 'Romans', '1CO': '1 Corinthians', '2CO': '2 Corinthians',
    'GAL': 'Galatians', 'EPH': 'Ephesians', 'PHP': 'Philippians', 'COL': 'Colossians',
    '1TH': '1 Thessalonians', '2TH': '2 Thessalonians', '1TI': '1 Timothy',
    '2TI': '2 Timothy', 'TIT': 'Titus', 'PHM': 'Philemon', 'HEB': 'Hebrews',
    'JAS': 'James', '1PE': '1 Peter', '2PE': '2 Peter', '1JN': '1 John',
    '2JN': '2 John', '3JN': '3 John', 'JUD': 'Jude', 'REV': 'Revelation'
}

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
    "Philippians": 50, "Colossians": 51, "Thessalonians": 52, "2 Thessalonians": 53,
    "1 Timothy": 54, "2 Timothy": 55, "Titus": 56, "Philemon": 57, "Hebrews": 58,
    "James": 59, "1 Peter": 60, "2 Peter": 61, "1 John": 62, "2 John": 63,
    "3 John": 64, "Jude": 65, "Revelation": 66
}

def get_or_create_book(book_name):
    """Get or create a book with proper position"""
    try:
        book = Book.objects.get(name=book_name)
        return book
    except Book.DoesNotExist:
        position = BOOK_POSITIONS.get(book_name, 99)
        book = Book.objects.create(
            name=book_name,
            slug=book_name.lower().replace(' ', '_').replace("'", ''),
            position=position
        )
        return book

def import_tniv_from_xml(xml_file, version_abbr):
    """Import TNIV from XML file"""
    
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
    
    # Parse XML
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        print(f"📖 Loaded {xml_file}")
    except Exception as e:
        print(f"❌ Error loading XML: {e}")
        return
    
    total_verses = 0
    new_verses = 0
    
    # Find all verse elements
    # Common XML formats: <verse>, <v>, <verse> with attributes
    for verse_elem in root.findall('.//verse'):
        # Get attributes
        book_abbr = verse_elem.get('book') or verse_elem.get('b')
        chapter = verse_elem.get('chapter') or verse_elem.get('c')
        verse_num = verse_elem.get('verse') or verse_elem.get('v')
        verse_text = verse_elem.text
        
        if not all([book_abbr, chapter, verse_num, verse_text]):
            continue
        
        # Get full book name
        book_name = BOOK_NAMES.get(book_abbr.upper(), book_abbr)
        
        try:
            # Get or create book
            book = get_or_create_book(book_name)
            
            # Get or create chapter
            chapter_obj, _ = Chapter.objects.get_or_create(
                book=book,
                number=int(chapter)
            )
            
            # Get or create verse
            verse_obj, _ = Verse.objects.get_or_create(
                chapter=chapter_obj,
                number=int(verse_num)
            )
            
            # Clean text
            verse_text = ' '.join(verse_text.split())
            
            # Check if verse text exists
            existing_verse = VerseText.objects.filter(
                bible_version=version,
                verse=verse_obj
            ).first()
            
            if not existing_verse:
                VerseText.objects.create(
                    bible_version=version,
                    verse=verse_obj,
                    text=verse_text
                )
                new_verses += 1
            
            total_verses += 1
            
            if total_verses % 1000 == 0:
                print(f"  Processed {total_verses:,} verses...")
                
        except Exception as e:
            print(f"  ⚠️ Error on {book_name} {chapter}:{verse_num}: {e}")
            continue
    
    print(f"\n✅ Import complete!")
    print(f"  Total verses processed: {total_verses:,}")
    print(f"  New verses: {new_verses:,}")
    print(f"  Total {version_abbr} verses: {VerseText.objects.filter(bible_version=version).count():,}")

def import_tniv_from_spb(spb_file, version_abbr):
    """Import TNIV from SPB file (SQLite format)"""
    import sqlite3
    
    try:
        # Try to connect to SPB as SQLite
        conn = sqlite3.connect(spb_file)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"📊 Tables found: {tables}")
        
        # Look for verses table
        if ('verses',) in tables or ('Verses',) in tables:
            table_name = 'verses' if ('verses',) in tables else 'Verses'
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
            columns = [description[0] for description in cursor.description]
            print(f"📊 Columns: {columns}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error reading SPB: {e}")
        print("SPB is likely a proprietary format. Try using the XML file instead.")

if __name__ == "__main__":
    # Try XML first
    if os.path.exists('data/TNIV.xml'):
        print("📖 Importing from TNIV.xml...")
        import_tniv_from_xml('data/TNIV.xml', 'TNIV')
    else:
        print("❌ TNIV.xml not found")
    
    # Also try SPB
    if os.path.exists('data/TNIV.spb'):
        print("\n📖 Also checking TNIV.spb...")
        import_tniv_from_spb('data/TNIV.spb', 'TNIV')
