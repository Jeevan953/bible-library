import os
import sys
import django
import json
import requests

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

def get_or_create_book(book_name):
    """Get or create a book"""
    book, created = Book.objects.get_or_create(
        name=book_name,
        defaults={'slug': book_name.lower()}
    )
    return book

def import_gnt_from_api():
    """Import GNT from bible-api.com"""
    
    # Get GNT version from database
    try:
        gnt_version = BibleVersion.objects.get(abbreviation='GNT')
        print(f"✅ Found GNT version: {gnt_version.name}")
    except BibleVersion.DoesNotExist:
        print("❌ GNT version not found in database")
        return
    
    # Check if already has verses
    existing = VerseText.objects.filter(bible_version=gnt_version).count()
    if existing > 0:
        print(f"⚠️ GNT already has {existing:,} verses")
        return
    
    # Books of the Bible
    books = [
        "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
        "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
        "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
        "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
        "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
        "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
        "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
        "Zephaniah", "Haggai", "Zechariah", "Malachi",
        "Matthew", "Mark", "Luke", "John", "Acts",
        "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
        "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
        "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
        "James", "1 Peter", "2 Peter", "1 John", "2 John",
        "3 John", "Jude", "Revelation"
    ]
    
    total_verses = 0
    
    for book_name in books:
        print(f"📖 Processing {book_name}...")
        
        # Get or create book
        book = get_or_create_book(book_name)
        
        # Fetch chapters for this book
        for chapter_num in range(1, 151):  # Max chapters
            try:
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
                    for verse_num, verse_text in verses_data.items():
                        # Get or create verse
                        verse, _ = Verse.objects.get_or_create(
                            chapter=chapter,
                            number=int(verse_num)
                        )
                        
                        # Create verse text
                        VerseText.objects.create(
                            bible_version=gnt_version,
                            verse=verse,
                            text=verse_text
                        )
                        total_verses += 1
                    
                    print(f"  ✅ Chapter {chapter_num}: {len(verses_data)} verses")
                else:
                    # No more chapters for this book
                    break
                    
            except Exception as e:
                break
    
    print(f"\n✅ Imported {total_verses:,} verses for GNT!")

if __name__ == "__main__":
    import_gnt_from_api()
