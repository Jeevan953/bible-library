import os
import sys
import django

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, Verse, Chapter
from django.db import transaction

# Sample data - Genesis 1:1-10
GENESIS_1_DATA = [
    (1, "In the beginning God created the heaven and the earth."),
    (2, "And the earth was without form, and void; and darkness was upon the face of the deep. And the Spirit of God moved upon the face of the waters."),
    (3, "And God said, Let there be light: and there was light."),
    (4, "And God saw the light, that it was good: and God divided the light from the darkness."),
    (5, "And God called the light Day, and the darkness he called Night. And the evening and the morning were the first day."),
    (6, "And God said, Let there be a firmament in the midst of the waters, and let it divide the waters from the waters."),
    (7, "And God made the firmament, and divided the waters which were under the firmament from the waters which were above the firmament: and it was so."),
    (8, "And God called the firmament Heaven. And the evening and the morning were the second day."),
    (9, "And God said, Let the waters under the heaven be gathered together unto one place, and let the dry land appear: and it was so."),
    (10, "And God called the dry land Earth; and the gathering together of the waters called he Seas: and God saw that it was good."),
]

def add_verses_to_version(version_abbr, book='Genesis', chapter_num=1, verse_data=GENESIS_1_DATA):
    """Add verses to an existing version"""
    try:
        version = BibleVersion.objects.get(abbreviation=version_abbr)
        
        # Find or create the chapter
        # First, check if there's a Chapter model
        try:
            from bible.models import Chapter
            chapter, created = Chapter.objects.get_or_create(
                book=book,
                number=chapter_num
            )
        except:
            # If no Chapter model, you might add verses directly
            chapter = None
        
        # Add verses
        added = 0
        for verse_num, verse_text in verse_data:
            try:
                if chapter:
                    Verse.objects.create(
                        chapter=chapter,
                        number=verse_num,
                        text=verse_text
                    )
                else:
                    # Direct creation without Chapter
                    Verse.objects.create(
                        version=version,  # Try this
                        book=book,
                        chapter=chapter_num,
                        verse=verse_num,
                        text=verse_text
                    )
                added += 1
            except Exception as e:
                print(f"  ⚠️ Error adding verse {verse_num}: {e}")
        
        print(f"✅ Added {added} verses to {version_abbr}")
        return True
        
    except BibleVersion.DoesNotExist:
        print(f"❌ Version {version_abbr} not found")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# Test with a version you know exists
test_version = 'KJV'  # Change to a version you have
if BibleVersion.objects.filter(abbreviation=test_version).exists():
    add_verses_to_version(test_version)
else:
    print(f"⚠️ {test_version} not found. Try another version")