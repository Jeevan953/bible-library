import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


REFERENCE_PATTERN = re.compile(
    r"^(.+?)\s+(\d+):(\d+)$"
)

BOOK_ALIASES = {
    "Psalm": "Psalms",
    "Song of Solomon": "Song of Songs",
}


class Command(BaseCommand):
    help = "Import the validated NIV clean TSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            help="Path to NIV_clean.tsv",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            raise CommandError(
                f"File not found: {file_path}"
            )

        records = {}

        with file_path.open(
            "r",
            encoding="utf-8-sig",
        ) as source:
            for line_number, raw_line in enumerate(
                source,
                start=1,
            ):
                line = raw_line.rstrip("\r\n")

                if not line:
                    continue

                if "\t" not in line:
                    raise CommandError(
                        f"Missing tab on line {line_number}"
                    )

                reference, text = line.split("\t", 1)
                match = REFERENCE_PATTERN.fullmatch(
                    reference.strip()
                )

                if not match:
                    raise CommandError(
                        f"Invalid reference on line "
                        f"{line_number}: {reference!r}"
                    )

                source_book = match.group(1).strip()
                book_name = BOOK_ALIASES.get(
                    source_book,
                    source_book,
                )
                chapter_number = int(match.group(2))
                verse_number = int(match.group(3))
                text = text.strip()

                key = (
                    book_name,
                    chapter_number,
                    verse_number,
                )

                if key in records:
                    raise CommandError(
                        f"Duplicate verse: {reference}"
                    )

                if not text:
                    raise CommandError(
                        f"Empty text: {reference}"
                    )

                records[key] = text

        if len(records) != 31085:
            raise CommandError(
                f"Expected 31085 verses, "
                f"parsed {len(records)}"
            )

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
                f"Expected 66 books, "
                f"parsed {len(parsed_books)}"
            )

        if len(parsed_chapters) != 1189:
            raise CommandError(
                f"Expected 1189 chapters, "
                f"parsed {len(parsed_chapters)}"
            )

        verse_map = {
            (
                verse.chapter.book.name,
                verse.chapter.number,
                verse.number,
            ): verse.id
            for verse in Verse.objects.select_related(
                "chapter__book"
            )
        }

        missing_positions = [
            key
            for key in records
            if key not in verse_map
        ]

        if missing_positions:
            raise CommandError(
                "Verse positions not found: "
                f"{missing_positions[:10]}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="NIV",
                    defaults={
                        "name": (
                            "New International Version"
                        ),
                        "language": "English",
                        "year": 1978,
                    },
                )
            )

            verse_texts = [
                VerseText(
                    bible_version=version,
                    verse_id=verse_map[key],
                    text=text,
                )
                for key, text in records.items()
            ]

            VerseText.objects.bulk_create(
                verse_texts,
                update_conflicts=True,
                update_fields=["text"],
                unique_fields=[
                    "bible_version",
                    "verse",
                ],
                batch_size=2000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})\n"
                f"Books: {len(parsed_books)}\n"
                f"Chapters: {len(parsed_chapters)}\n"
                f"Verses: {len(records)}"
            )
        )
