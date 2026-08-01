import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


REFERENCE_PATTERN = re.compile(
    r"^(.+?)\s+(\d+):(\d+)(?:\t(.*))?$"
)

EXPECTED_EMPTY = {
    (40, 23, 14),  # Matthew 23:14
    (44, 8, 37),   # Acts 8:37
    (44, 15, 34),  # Acts 15:34
}


class Command(BaseCommand):
    help = "Import the Darby Bible Translation."

    def add_arguments(self, parser):
        parser.add_argument("filename", type=str)

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        pdf_path = path.parent / "dbt.pdf"

        if not pdf_path.is_file():
            raise CommandError(f"PDF not found: {pdf_path}")

        content = path.read_text(encoding="utf-8-sig")

        book_positions = {}
        source_rows = {}
        reference_keys = set()
        empty_keys = set()
        headers = []
        duplicates = []
        blank_lines = 0

        for line_number, raw_line in enumerate(
            content.splitlines(),
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                blank_lines += 1
                continue

            match = REFERENCE_PATTERN.match(line)

            if not match:
                headers.append((line_number, line))
                continue

            book_name = match.group(1).strip()
            chapter_number = int(match.group(2))
            verse_number = int(match.group(3))
            text = (match.group(4) or "").strip()

            if book_name not in book_positions:
                book_positions[book_name] = (
                    len(book_positions) + 1
                )

            key = (
                book_positions[book_name],
                chapter_number,
                verse_number,
            )

            if key in reference_keys:
                duplicates.append(
                    f"{book_name} "
                    f"{chapter_number}:{verse_number}"
                )
                continue

            reference_keys.add(key)

            if text:
                source_rows[key] = text
            else:
                empty_keys.add(key)

        canonical = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.select_related(
                "chapter",
                "chapter__book",
            )
        }

        canonical_keys = set(canonical)
        missing = canonical_keys - reference_keys
        extra = reference_keys - canonical_keys

        chapters = {
            (position, chapter)
            for position, chapter, verse in reference_keys
        }

        errors = []

        if len(headers) != 2:
            errors.append(
                f"Expected 2 header lines, found {len(headers)}"
            )

        if len(book_positions) != 66:
            errors.append(
                f"Expected 66 books, found {len(book_positions)}"
            )

        if len(chapters) != 1189:
            errors.append(
                f"Expected 1189 chapters, found {len(chapters)}"
            )

        if len(reference_keys) != 31102:
            errors.append(
                "Expected 31102 reference positions, found "
                f"{len(reference_keys)}"
            )

        if len(source_rows) != 31099:
            errors.append(
                "Expected 31099 verse texts, found "
                f"{len(source_rows)}"
            )

        if empty_keys != EXPECTED_EMPTY:
            errors.append(
                "Empty positions differ from expected. "
                f"Found: {sorted(empty_keys)}"
            )

        if duplicates:
            errors.append(
                f"Duplicate references: {len(duplicates)}"
            )

        if missing:
            errors.append(
                f"Missing canonical positions: {sorted(missing)}"
            )

        if extra:
            errors.append(
                f"Extra source positions: {sorted(extra)}"
            )

        if "\ufffd" in content:
            errors.append(
                "Replacement characters found in the text"
            )

        if errors:
            raise CommandError(
                "DBT validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="DBT",
                    defaults={
                        "name": "Darby Bible Translation",
                        "language": "English",
                        "year": 1890,
                        "description": (
                            "The Bible translation by "
                            "John Nelson Darby."
                        ),
                        "pdf_filename": "dbt.pdf",
                    },
                )
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            verse_texts = [
                VerseText(
                    bible_version=version,
                    verse=canonical[key],
                    text=text,
                )
                for key, text in source_rows.items()
            ]

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=2000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})"
            )
        )
        self.stdout.write("Books: 66")
        self.stdout.write("Chapters: 1189")
        self.stdout.write(f"Verses: {len(verse_texts)}")
        self.stdout.write(
            f"Empty verse positions: {len(empty_keys)}"
        )
        self.stdout.write(
            f"Ignored header lines: {len(headers)}"
        )
        self.stdout.write(
            f"Ignored blank lines: {blank_lines}"
        )
