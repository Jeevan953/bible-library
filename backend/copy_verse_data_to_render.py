import os
import sys
import django

sys.path.append('/home/jeevan/PythonProjects/bible_fullstack/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bible.models import BibleVersion, VerseText

# New versions that need verse data
new_versions = ['ESV', 'NLT', 'CSB', 'NASB', 'RSV', 'GNT', 'AMP', 'MSG', 'TLB', 'NET']

# Source version
source_abbr = 'KJV'

try:
    source = BibleVersion.objects.get(abbreviation=source_abbr)
    print(f"📖 Source: {source_abbr} has {VerseText.objects.filter(bible_version=source).count():,} verses")
    
    for abbr in new_versions:
        try:
            target = BibleVersion.objects.get(abbreviation=abbr)
            
            # Check if target already has verses
            existing = VerseText.objects.filter(bible_version=target).count()
            if existing > 0:
                print(f"⚠️ {abbr} already has {existing:,} verses")
                continue
            
            print(f"\n📝 Copying verses to {abbr}...")
            
            # Get all verse texts from source
            source_texts = VerseText.objects.filter(bible_version=source)
            count = 0
            
            for st in source_texts:
                VerseText.objects.create(
                    bible_version=target,
                    verse=st.verse,
                    text=st.text
                )
                count += 1
                
                if count % 5000 == 0:
                    print(f"  Copied {count:,} verses...")
            
            print(f"✅ Copied {count:,} verses to {abbr}")
            
        except BibleVersion.DoesNotExist:
            print(f"❌ Version {abbr} not found in database")
            
except BibleVersion.DoesNotExist:
    print(f"❌ Source version {source_abbr} not found")

print("\n✅ All done!")
