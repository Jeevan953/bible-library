import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


REFERENCE_PATTERN = re.compile(
    r"^(.+?)\s+(\d+):(\d+)(?:\t(.*))?$"
)

# MSB places the Romans doxology after chapter 14.
VERSE_REMAP = {
    (45, 14, 24): (45, 16, 25),
    (45, 14, 25): (45, 16, 26),
    (45, 14, 26): (45, 16, 27),
}

EXPECTED_EMPTY = {
    (42, 17, 36),  # Luke 17:36
    (44, 8, 37),   # Acts 8:37
    (44, 15, 34),  # Acts 15:34
    (44, 24, 7),   # Acts 24:7
}


class Command(BaseCommand):
    help = "Import the Majority Standard Bible text file."

    def add_arguments(self, parser):
        parser.add_argument("filename", type=str)

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        try:
            content = path.read_bytes().decode("cp1252")
        except UnicodeDecodeError as error:
            raise CommandError(
                f"Unable to decode {path} as cp1252: {error}"
            ) from error

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

            source_key = (
                book_positions[book_name],
                chapter_number,
                verse_number,
            )

            canonical_key = VERSE_REMAP.get(
                source_key,
                source_key,
            )

            if canonical_key in reference_keys:
                duplicates.append(
                    f"{book_name} "
                    f"{chapter_number}:{verse_number}"
                )
                continue

            reference_keys.add(canonical_key)

            if text:
                source_rows[canonical_key] = text
            else:
                empty_keys.add(canonical_key)

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

        if len(headers) != 3:
            errors.append(
                f"Expected 3 header lines, found {len(headers)}"
            )

        if len(book_positions) != 66:
            errors.append(
                f"Expected 66 books, found {len(book_positions)}"
            )

        if len(chapters) != 1189:
            errors.append(
                f"Expected 1189 chapters, found {len(chapters)}"
            )

        if duplicates:
            errors.append(
                f"Duplicate references: {len(duplicates)}"
            )

        if empty_keys != EXPECTED_EMPTY:
            errors.append(
                "Unexpected empty references. "
                f"Found: {sorted(empty_keys)}"
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
                "Replacement characters were found in the text"
            )

        if errors:
            raise CommandError(
                "MSB validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="MSB",
                    defaults={
                        "name": "Majority Standard Bible",
                        "language": "English",
                        "description": (
                            "Majority Standard Bible."
                        ),
                        "pdf_filename": "MSB.pdf",
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
        self.stdout.write(
            f"Verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Empty verse positions: {len(empty_keys)}"
        )
        self.stdout.write(
            f"Remapped verses: {len(VERSE_REMAP)}"
        )
        self.stdout.write(
            f"Ignored header lines: {len(headers)}"
        )
        self.stdout.write(
            f"Ignored blank lines: {blank_lines}"
        )
