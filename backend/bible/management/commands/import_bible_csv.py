from django.core.management.base import BaseCommand
from bible.models import BibleVersion, Verse
import csv

class Command(BaseCommand):
    help = 'Import Bible versions from CSV files'
    
    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='CSV file path')
        parser.add_argument('--abbr', type=str, help='Version abbreviation')
        parser.add_argument('--name', type=str, help='Version full name')
    
    def handle(self, *args, **options):
        file_path = options.get('file')
        version_abbr = options.get('abbr')
        version_name = options.get('name', version_abbr)
        
        if not file_path or not version_abbr:
            self.stdout.write("❌ Please specify --file and --abbr")
            return
        
        # Check if version exists
        if BibleVersion.objects.filter(abbreviation=version_abbr).exists():
            self.stdout.write(f"⚠️ Version {version_abbr} already exists")
            return
        
        # Create version
        version = BibleVersion.objects.create(
            abbreviation=version_abbr,
            name=version_name,
            description=f"Imported from CSV",
            language='English',
            year=2024
        )
        
        # Import verses from CSV
        count = 0
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                Verse.objects.create(
                    version=version,
                    book=row['book'],
                    chapter=int(row['chapter']),
                    verse=int(row['verse']),
                    text=row['text']
                )
                count += 1
        
        self.stdout.write(f"✅ Imported {version_abbr} with {count} verses from {file_path}")