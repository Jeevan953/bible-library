import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from bible.models import BibleVersion, Book, Chapter, Verse, VerseText


BOOKS = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalms",
    "Proverbs",
    "Ecclesiastes",
    "Song of Songs",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
]

BOOK_ALIASES = {
    "Psalm": "Psalms",
    "Song of Solomon": "Song of Songs",
}

BOOK_POSITIONS = {
    book_name: position
    for position, book_name in enumerate(BOOKS, start=1)
}

REFERENCE_PATTERN = re.compile(r"^(.+?)\s+(\d+):(\d+)$")


class Command(BaseCommand):
    help = "Import the Catholic Public Domain Version from a tab-separated verse file."

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to the CPDV text file")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        records = {}
        ignored_lines = 0

        with file_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as source:
            for line_number, raw_line in enumerate(source, start=1):
                line = raw_line.rstrip("\r\n")

                if not line.strip():
                    ignored_lines += 1
                    continue

                if "\t" not in line:
                    ignored_lines += 1
                    continue

                reference, text = line.split("\t", 1)
                reference = reference.strip()
                text = text.strip()

                match = REFERENCE_PATTERN.fullmatch(reference)

                if not match:
                    raise CommandError(
                        f"Invalid reference on line {line_number}: "
                        f"{reference!r}"
                    )

                source_book = match.group(1).strip()
                book_name = BOOK_ALIASES.get(source_book, source_book)
                chapter_number = int(match.group(2))
                verse_number = int(match.group(3))

                if book_name not in BOOK_POSITIONS:
                    raise CommandError(
                        f"Unknown book on line {line_number}: "
                        f"{source_book!r}"
                    )

                if not text:
                    raise CommandError(
                        f"Empty verse text on line {line_number}: "
                        f"{reference}"
                    )

                verse_key = (
                    book_name,
                    chapter_number,
                    verse_number,
                )

                if verse_key in records:
                    raise CommandError(
                        f"Duplicate verse on line {line_number}: "
                        f"{reference}"
                    )

                records[verse_key] = text

        parsed_books = {
            book_name
            for book_name, _, _ in records
        }

        parsed_chapters = {
            (book_name, chapter_number)
            for book_name, chapter_number, _ in records
        }

        if len(parsed_books) != 66:
            raise CommandError(
                f"Expected 66 books, parsed {len(parsed_books)}"
            )

        if len(parsed_chapters) != 1189:
            raise CommandError(
                f"Expected 1189 chapters, parsed "
                f"{len(parsed_chapters)}"
            )

        if len(records) != 31102:
            raise CommandError(
                f"Expected 31102 verses, parsed {len(records)}"
            )

        with transaction.atomic():
            version, version_created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="CPDV",
                    defaults={
                        "name": "Catholic Public Domain Version",
                        "language": "English",
                        "year": 2009,
                        "pdf_filename": "cpdv.pdf",
                    },
                )
            )

            book_map = {}

            for position, book_name in enumerate(BOOKS, start=1):
                book, _ = Book.objects.update_or_create(
                    position=position,
                    defaults={
                        "name": book_name,
                        "slug": slugify(book_name),
                    },
                )
                book_map[book_name] = book

            required_chapters = {
                (
                    book_map[book_name].id,
                    chapter_number,
                )
                for book_name, chapter_number in parsed_chapters
            }

            Chapter.objects.bulk_create(
                [
                    Chapter(
                        book_id=book_id,
                        number=chapter_number,
                    )
                    for book_id, chapter_number in required_chapters
                ],
                ignore_conflicts=True,
                batch_size=2000,
            )

            chapter_map = {
                (chapter.book_id, chapter.number): chapter
                for chapter in Chapter.objects.filter(
                    book_id__in=[
                        book.id for book in book_map.values()
                    ]
                )
            }

            required_verses = set()

            for book_name, chapter_number, verse_number in records:
                book = book_map[book_name]
                chapter = chapter_map[
                    (book.id, chapter_number)
                ]

                required_verses.add(
                    (chapter.id, verse_number)
                )

            Verse.objects.bulk_create(
                [
                    Verse(
                        chapter_id=chapter_id,
                        number=verse_number,
                    )
                    for chapter_id, verse_number in required_verses
                ],
                ignore_conflicts=True,
                batch_size=2000,
            )

            chapter_ids = {
                chapter_id
                for chapter_id, _ in required_verses
            }

            verse_map = {
                (verse.chapter_id, verse.number): verse.id
                for verse in Verse.objects.filter(
                    chapter_id__in=chapter_ids
                )
            }

            verse_texts = []

            for (
                book_name,
                chapter_number,
                verse_number,
            ), text in records.items():
                book = book_map[book_name]
                chapter = chapter_map[
                    (book.id, chapter_number)
                ]
                verse_id = verse_map[
                    (chapter.id, verse_number)
                ]

                verse_texts.append(
                    VerseText(
                        bible_version=version,
                        verse_id=verse_id,
                        text=text,
                    )
                )

            VerseText.objects.bulk_create(
                verse_texts,
                update_conflicts=True,
                update_fields=["text"],
                unique_fields=["bible_version", "verse"],
                batch_size=2000,
            )

        action = "Created" if version_created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})\n"
                f"Books: {len(parsed_books)}\n"
                f"Chapters: {len(parsed_chapters)}\n"
                f"Verses: {len(records)}\n"
                f"Ignored header lines: {ignored_lines}"
            )
        )
