import os
import sys
import django

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText, Book, Chapter, Verse

print("📊 BIBLE LIBRARY STATISTICS")
print("=" * 60)

total_versions = BibleVersion.objects.count()
total_verse_texts = VerseText.objects.count()
total_books = Book.objects.count()
total_chapters = Chapter.objects.count()
total_verses = Verse.objects.count()

print(f"📚 Bible Versions: {total_versions}")
print(f"📖 Verse Texts: {total_verse_texts:,}")
print(f"📕 Books: {total_books}")
print(f"📗 Chapters: {total_chapters}")
print(f"📘 Verses: {total_verses}")
print()

print("📋 Versions by Year:")
for version in BibleVersion.objects.all().order_by('-year'):
    count = VerseText.objects.filter(bible_version=version).count()
    print(f"  {version.year}  {version.abbreviation:6} {version.name[:30]:30} ({count:,} verses)")

print()
print("📚 Total Unique Verses: {:,}".format(total_verses))
print("📖 Average Verses per Version: {:,}".format(total_verse_texts // total_versions if total_versions > 0 else 0))