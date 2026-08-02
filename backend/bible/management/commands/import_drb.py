import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


REFERENCE_PATTERN = re.compile(
    r"^(.+?)\s+(\d+):(\d+)(?:\t(.*))?$"
)

EXPECTED_HEADERS = [
    (1, "DRB"),
    (2, "Douay-Rheims Bible"),
]

EXPECTED_EMPTY_KEYS = {
    (1, 27, 23),
    (1, 49, 32),
    (2, 9, 21),
    (2, 40, 14),
    (2, 40, 15),
    (3, 26, 46),
    (4, 11, 35),
    (18, 32, 18),
    (18, 40, 4),
    (22, 1, 1),
}

class Command(BaseCommand):
    help = "Import Douay-Rheims Bible."

    def add_arguments(self, parser):
        parser.add_argument("filename", type=str)

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        pdf_path = path.parent / "drb.pdf"

        if not pdf_path.is_file():
            raise CommandError(f"PDF not found: {pdf_path}")

        content = path.read_text(encoding="utf-8-sig")

        book_positions = {}
        source_rows = {}
        reference_keys = set()
        headers = []
        duplicates = []
        empty_keys = set()
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

        if headers != EXPECTED_HEADERS:
            errors.append(
                f"Expected headers {EXPECTED_HEADERS!r}, "
                f"found {headers!r}"
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

        if len(source_rows) != 31092:
            errors.append(
                "Expected 31092 verse texts, found "
                f"{len(source_rows)}"
            )

        if empty_keys != EXPECTED_EMPTY_KEYS:
            unexpected_empty = (
                empty_keys - EXPECTED_EMPTY_KEYS
            )
            missing_empty = (
                EXPECTED_EMPTY_KEYS - empty_keys
            )

            errors.append(
                "Empty positions differ from expected. "
                f"Unexpected: {sorted(unexpected_empty)}; "
                f"missing: {sorted(missing_empty)}"
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
                "DRB validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="DRB",
                    defaults={
                        "name": "Douay-Rheims Bible",
                        "language": "English",
                        "year": None,
                        "description": (
                            "Douay-Rheims Bible imported from the "
                            "complete DRB plain-text source."
                        ),
                        "pdf_filename": "drb.pdf",
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
            f"Ignored header lines: {len(headers)}"
        )

        self.stdout.write(
            f"Empty verse positions: {len(empty_keys)}"
        )
        self.stdout.write(
            f"Ignored blank lines: {blank_lines}"
        )
