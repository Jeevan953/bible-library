import os
import sys
import django
import requests
import time

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

# Books of the Bible (Old and New Testament)
BOOKS = [
    # Old Testament
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    # New Testament
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation"
]

# Chapter counts for each book (to know when to stop)
MAX_CHAPTERS = {
    "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34,
    "Joshua": 24, "Judges": 21, "Ruth": 4, "1 Samuel": 31, "2 Samuel": 24,
    "1 Kings": 22, "2 Kings": 25, "1 Chronicles": 29, "2 Chronicles": 36, "Ezra": 10,
    "Nehemiah": 13, "Esther": 10, "Job": 42, "Psalms": 150, "Proverbs": 31,
    "Ecclesiastes": 12, "Song of Solomon": 8, "Isaiah": 66, "Jeremiah": 52, "Lamentations": 5,
    "Ezekiel": 48, "Daniel": 12, "Hosea": 14, "Joel": 3, "Amos": 9,
    "Obadiah": 1, "Jonah": 4, "Micah": 7, "Nahum": 3, "Habakkuk": 3,
    "Zephaniah": 3, "Haggai": 2, "Zechariah": 14, "Malachi": 4,
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28,
    "Romans": 16, "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6, "Ephesians": 6,
    "Philippians": 4, "Colossians": 4, "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13,
    "James": 5, "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1,
    "3 John": 1, "Jude": 1, "Revelation": 22
}

def import_gnt_complete():
    """Complete GNT import using Bible API"""
    
    # Get GNT version
    try:
        gnt_version = BibleVersion.objects.get(abbreviation='GNT')
        print(f"✅ Found GNT version: {gnt_version.name}")
    except BibleVersion.DoesNotExist:
        print("❌ GNT version not found")
        return
    
    # Count existing verses
    existing = VerseText.objects.filter(bible_version=gnt_version).count()
    print(f"📊 Existing GNT verses: {existing:,}")
    
    total_verses = 0
    new_verses = 0
    
    for book_name in BOOKS:
        print(f"\n📖 Processing {book_name}...")
        
        # Get or create book
        book, created = Book.objects.get_or_create(
            name=book_name,
            defaults={'slug': book_name.lower().replace(' ', '_')}
        )
        
        max_chapter = MAX_CHAPTERS.get(book_name, 50)
        
        for chapter_num in range(1, max_chapter + 1):
            try:
                # Try to fetch from API
                url = f"https://bible-api.com/{book_name.replace(' ', '%20')}%20{chapter_num}?translation=gnt"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Get or create chapter
                    chapter, _ = Chapter.objects.get_or_create(
                        book=book,
                        number=chapter_num
                    )
                    
                    # Process verses
                    verses_data = data.get('verses', {})
                    if verses_data:
                        for verse_num, verse_text in verses_data.items():
                            # Check if this verse already exists
                            verse, _ = Verse.objects.get_or_create(
                                chapter=chapter,
                                number=int(verse_num)
                            )
                            
                            # Check if verse text already exists for GNT
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
                        
                        print(f"  ✅ Chapter {chapter_num}: {len(verses_data)} verses")
                    else:
                        print(f"  ⚠️ Chapter {chapter_num}: No verses found")
                        
                else:
                    print(f"  ❌ Chapter {chapter_num}: Status {response.status_code}")
                    
                # Rate limiting - be nice to the API
                time.sleep(0.1)
                
            except Exception as e:
                print(f"  ❌ Error on {book_name} {chapter_num}: {e}")
                continue
    
    print(f"\n📊 Import complete!")
    print(f"  Total verses processed: {total_verses:,}")
    print(f"  New verses added: {new_verses:,}")
    print(f"  Total GNT verses: {VerseText.objects.filter(bible_version=gnt_version).count():,}")

if __name__ == "__main__":
    import_gnt_complete()
