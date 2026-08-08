import os
import sys
import django
import json

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Verse, Chapter, Book

def import_version_from_json(file_path, version_abbr):
    """Import a Bible version from a JSON file"""
    
    # Get the version
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        print(f"✅ Found {version_abbr} version: {version.name}")
    except BibleVersion.DoesNotExist:
        print(f"❌ {version_abbr} version not found")
        return
    
    # Check if already has verses
    existing = VerseText.objects.filter(bible_version=version).count()
    if existing > 30000:
        print(f"✅ {version_abbr} already has {existing:,} verses (complete)")
        return
    
    if existing > 0:
        print(f"⚠️ {version_abbr} has {existing:,} verses (partial) - will update")
        # Optionally delete partial data
        # VerseText.objects.filter(bible_version=version).delete()
    
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
    
    # Handle different JSON formats
    if isinstance(data, dict):
        # Check if it's a dictionary with book keys
        if 'books' in data:
            # Format with 'books' key
            books_data = data['books']
        else:
            # Assume dictionary where keys are book names
            books_data = data
    
    elif isinstance(data, list):
        # List format - process each item
        print("📝 Processing list format...")
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
            
            if total_verses % 1000 == 0:
                print(f"  Processed {total_verses:,} verses...")
        
        print(f"✅ Import complete!")
        print(f"  Total verses: {total_verses:,}")
        print(f"  New verses: {new_verses:,}")
        print(f"  Total {version_abbr} verses: {VerseText.objects.filter(bible_version=version).count():,}")
        return
    
    # Process dictionary format
    for book_name, book_data in books_data.items():
        print(f"📖 Processing {book_name}...")
        
        # Get or create book
        book, _ = Book.objects.get_or_create(
            name=book_name,
            defaults={'slug': book_name.lower().replace(' ', '_')}
        )
        
        # Check if book_data is dict with chapters
        if isinstance(book_data, dict):
            for chapter_num, chapter_data in book_data.items():
                if isinstance(chapter_data, dict) and 'verses' in chapter_data:
                    verses = chapter_data['verses']
                elif isinstance(chapter_data, dict):
                    verses = chapter_data
                else:
                    continue
                
                # Get or create chapter
                chapter, _ = Chapter.objects.get_or_create(
                    book=book,
                    number=int(chapter_num)
                )
                
                for verse_num, verse_text in verses.items():
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
        
        elif isinstance(book_data, list):
            # List of chapters
            for chapter_data in book_data:
                chapter_num = chapter_data.get('chapter')
                verses = chapter_data.get('verses', {})
                
                if not chapter_num:
                    continue
                
                # Get or create chapter
                chapter, _ = Chapter.objects.get_or_create(
                    book=book,
                    number=int(chapter_num)
                )
                
                for verse_num, verse_text in verses.items():
                    # Get or create verse
                    verse, _ = Verse.objects.get_or_create(
                        chapter=chapter,
                        number=int(verse_num)
                    )
                    
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
        
        print(f"  ✅ {book_name}: {len(verses) if isinstance(verses, dict) else 'processed'} verses")
    
    print(f"\n✅ Import complete!")
    print(f"  Total verses: {total_verses:,}")
    print(f"  New verses: {new_verses:,}")
    print(f"  Total {version_abbr} verses: {VerseText.objects.filter(bible_version=version).count():,}")

if __name__ == "__main__":
    # Import ESV
    import_version_from_json('data/ESV.json', 'ESV')
