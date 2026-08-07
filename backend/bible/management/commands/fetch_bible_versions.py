from pathlib import Path

from django.db import transaction

from bible.models import BibleVersion, Book, Verse, VerseText

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
import requests
import json
import os
from datetime import datetime


class Command(BaseCommand):
    help = 'Fetch additional Bible versions from various sources'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            choices=['stepbible', 'bible-api', 'local'],
            default='bible-api',
            help='Source to fetch Bible versions from'
        )
        parser.add_argument(
            '--versions',
            type=str,
            help='Comma-separated list of version abbreviations to add'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List available versions from the source'
        )
    
    def handle(self, *args, **options):
        source = options['source']
        version_list = options.get('versions')
        list_available = options.get('list')
        
        if list_available:
            self.list_available_versions(source)
            return
        
        if version_list:
            versions = [v.strip() for v in version_list.split(',')]
        else:
            # Default versions to add if none specified
            versions = ['NIV', 'ESV', 'NLT', 'CSB', 'NASB', 'RSV', 'GNT', 'AMP', 'MSG']
        
        self.stdout.write(f"📖 Adding {len(versions)} Bible versions from {source}")
        self.stdout.write("=" * 50)
        
        for version_abbr in versions:
            self.add_version(version_abbr, source)
    
    def list_available_versions(self, source):
        """List all available versions from the source"""
        self.stdout.write(f"📚 Available versions from {source}:")
        self.stdout.write("=" * 50)
        
        if source == 'bible-api':
            try:
                # Try to get versions from bible-api.com
                response = requests.get('https://bible-api.com/data/versions', timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for v in data.get('versions', []):
                        self.stdout.write(f"  - {v.get('abbreviation')}: {v.get('name')}")
                else:
                    self.stdout.write("❌ Could not fetch version list")
            except Exception as e:
                self.stdout.write(f"❌ Error: {str(e)}")
                self.stdout.write("\n📌 Popular versions you can add:")
                versions = [
                    ('NIV', 'New International Version'),
                    ('ESV', 'English Standard Version'),
                    ('NLT', 'New Living Translation'),
                    ('CSB', 'Christian Standard Bible'),
                    ('NASB', 'New American Standard Bible'),
                    ('RSV', 'Revised Standard Version'),
                    ('GNT', 'Good News Translation'),
                    ('AMP', 'Amplified Bible'),
                    ('MSG', 'The Message Bible'),
                    ('TLB', 'The Living Bible'),
                    ('NET', 'New English Translation'),
                    ('LSV', 'Literal Standard Version'),
                    ('WEB', 'World English Bible'),
                    ('YLT', "Young's Literal Translation"),
                    ('ASV', 'American Standard Version'),
                ]
                for abbr, name in versions:
                    self.stdout.write(f"  - {abbr}: {name}")
    
    def add_version(self, version_abbr, source):
        """Add a specific Bible version"""
        self.stdout.write(f"\n⏳ Adding {version_abbr}...", ending='')
        
        try:
            # Check if version already exists using 'abbreviation' field
            if BibleVersion.objects.filter(abbreviation=version_abbr).exists():
                self.stdout.write(" ℹ️ Already exists")
                return
            
            if source == 'bible-api':
                success = self.fetch_from_bible_api(version_abbr)
            elif source == 'stepbible':
                success = self.fetch_from_stepbible(version_abbr)
            else:
                success = self.fetch_from_local(version_abbr)
            
            if success:
                self.stdout.write(" ✅ Added successfully")
            else:
                self.stdout.write(" ❌ Failed")
                
        except Exception as e:
            self.stdout.write(f" ❌ Error: {str(e)}")
    
    def fetch_from_bible_api(self, version_abbr):
        """Fetch a version from bible-api.com"""
        try:
            # Using the free bible-api.com
            # Note: This might not have all versions, but it's a good starting point
            api_url = f"https://bible-api.com/data/{version_abbr.lower()}"
            
            self.stdout.write(f" Fetching from {api_url}...", ending='')
            response = requests.get(api_url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.stdout.write(" Success!", ending='')
                
                # Create version using your model's fields
                version = BibleVersion.objects.create(
                    abbreviation=version_abbr.upper(),
                    name=data.get('name', self.get_version_name(version_abbr)),
                    description=f"{self.get_version_name(version_abbr)} - Added via Bible-API",
                    language='English',
                    year=data.get('year', datetime.now().year)
                )
                
                # Parse and save verses
                books_data = data.get('books', {})
                verse_count = 0
                
                for book_name, book_data in books_data.items():
                    chapters = book_data.get('chapters', [])
                    for chapter_num, chapter_data in enumerate(chapters, 1):
                        verses = chapter_data.get('verses', [])
                        for verse_num, verse_text in enumerate(verses, 1):
                            Verse.objects.create(
                                version=version,
                                book=book_name,
                                chapter=chapter_num,
                                verse=verse_num,
                                text=verse_text
                            )
                            verse_count += 1
                
                self.stdout.write(f" ({verse_count} verses saved)")
                return True
                
            elif response.status_code == 404:
                self.stdout.write(" Version not available on Bible-API")
                return False
            else:
                self.stdout.write(f" API returned status {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.stdout.write(" Timeout - API took too long")
            return False
        except Exception as e:
            self.stdout.write(f" Error: {str(e)}")
            return False
    
    def fetch_from_stepbible(self, version_abbr):
        """Fetch a version from STEPBible API"""
        # Placeholder - implement based on STEPBible API docs
        self.stdout.write(" STEPBible implementation coming soon...")
        return False
    
    def fetch_from_local(self, version_abbr):
        """Fetch from local data files"""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        file_path = os.path.join(data_dir, f'{version_abbr}.json')
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    
                version = BibleVersion.objects.create(
                    abbreviation=version_abbr.upper(),
                    name=data.get('name', version_abbr),
                    description=f"Added from local file",
                    language='English',
                    year=data.get('year', datetime.now().year)
                )
                
                # Parse based on your data structure
                for book_data in data.get('books', []):
                    for chapter_data in book_data.get('chapters', []):
                        for verse_data in chapter_data.get('verses', []):
                            Verse.objects.create(
                                version=version,
                                book=book_data['name'],
                                chapter=chapter_data['number'],
                                verse=verse_data['number'],
                                text=verse_data['text']
                            )
                return True
            except Exception as e:
                self.stdout.write(f" Error parsing file: {str(e)}")
                return False
        else:
            self.stdout.write(f" No local data file found")
            return False
    
    def get_version_name(self, abbr):
        """Get full name for version abbreviation"""
        names = {
            'NIV': 'New International Version',
            'ESV': 'English Standard Version',
            'NLT': 'New Living Translation',
            'CSB': 'Christian Standard Bible',
            'NASB': 'New American Standard Bible',
            'RSV': 'Revised Standard Version',
            'GNT': 'Good News Translation',
            'AMP': 'Amplified Bible',
            'MSG': 'The Message Bible',
            'TLB': 'The Living Bible',
            'NET': 'New English Translation',
            'LSV': 'Literal Standard Version',
            'WEB': 'World English Bible',
            'YLT': "Young's Literal Translation",
            'ASV': 'American Standard Version',
            'KJV': 'King James Version',
            'JST': 'Joseph Smith Translation',
            'WYC': 'Wycliffe Bible',
            'TYN': 'Tyndale Bible',
            'GENEVA': 'Geneva Bible',
            'DBT': 'Darby Bible Translation',
            'DRB': 'Douay-Rheims Bible',
            'EMTV': 'English Majority Text Version',
            'JUB': 'Jubilee Bible',
            'LEB': 'Lexham English Bible',
            'NHEB': 'New Heart English Bible',
            'OTCV': 'Open Testament Church Version',
            'WE': 'World English Bible',
            'WM': 'Weymouth New Testament',
            'YLT': "Young's Literal Translation",
        }
        return names.get(abbr.upper(), abbr)
