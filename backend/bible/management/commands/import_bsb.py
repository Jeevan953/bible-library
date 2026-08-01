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
    help = "Import the Berean Standard Bible TSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            help="Path to BSB.txt",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            raise CommandError(
                f"File not found: {file_path}"
            )

        records = {}
        all_positions = set()
        empty_positions = 0
        header_lines = 0

        with file_path.open(
            "r",
            encoding="utf-8-sig",
        ) as source:
            for line_number, raw_line in enumerate(
                source,
                start=1,
            ):
                line = raw_line.rstrip("\r\n")

                if line_number <= 3:
                    header_lines += 1
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

                key = (
                    book_name,
                    chapter_number,
                    verse_number,
                )

                if key in all_positions:
                    raise CommandError(
                        f"Duplicate verse: {reference}"
                    )

                all_positions.add(key)
                text = text.strip()

                if not text:
                    empty_positions += 1
                    continue

                records[key] = text

        parsed_books = {
            book_name
            for book_name, _, _ in all_positions
        }

        parsed_chapters = {
            (book_name, chapter_number)
            for book_name, chapter_number, _ in all_positions
        }

        if len(all_positions) != 31102:
            raise CommandError(
                f"Expected 31102 verse positions, "
                f"parsed {len(all_positions)}"
            )

        if len(records) != 31086:
            raise CommandError(
                f"Expected 31086 verse texts, "
                f"parsed {len(records)}"
            )

        if empty_positions != 16:
            raise CommandError(
                f"Expected 16 empty positions, "
                f"found {empty_positions}"
            )

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
            for key in all_positions
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
                    abbreviation="BSB",
                    defaults={
                        "name": "Berean Standard Bible",
                        "language": "English",
                        "year": 2020,
                    },
                )
            )

            version.verse_texts.all().delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse_id=verse_map[key],
                        text=text,
                    )
                    for key, text in records.items()
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
                f"Verses: {len(records)}\n"
                f"Empty verse positions: "
                f"{empty_positions}\n"
                f"Ignored header lines: {header_lines}"
            )
        )
