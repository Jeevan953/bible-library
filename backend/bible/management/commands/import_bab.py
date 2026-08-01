import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


REFERENCE_PATTERN = re.compile(
    r"^(.+?)\s+(\d+):(\d+)(?:\t(.*))?$"
)
OMITTED_VERSES = {
    (40, 17, 21),
    (40, 18, 11),
    (40, 23, 14),
    (41, 7, 16),
    (41, 9, 44),
    (41, 9, 46),
    (41, 11, 26),
    (41, 15, 28),
    (42, 17, 36),
    (42, 23, 17),
    (43, 5, 4),
    (44, 8, 37),
    (44, 15, 34),
    (44, 24, 7),
    (44, 28, 29),
    (45, 16, 24),
}


class Command(BaseCommand):
    help = "Import the Berean Annotated Bible text file."

    def add_arguments(self, parser):
        parser.add_argument("file", type=str)

    def handle(self, *args, **options):
        path = Path(options["file"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        pdf_path = path.with_name("BAB.pdf")

        if not pdf_path.is_file():
            raise CommandError(f"PDF not found: {pdf_path}")

        book_order = []
        book_positions = {}
        source_rows = []
        source_keys = set()

        header_lines = []
        blank_lines = 0
        duplicates = []
        empty_references = set()

        for line_number, raw_line in enumerate(
            path.read_text(
                encoding="utf-8-sig"
            ).splitlines(),
            start=1,
        ):
            line = raw_line.rstrip()

            if not line.strip():
                blank_lines += 1
                continue

            match = REFERENCE_PATTERN.match(line)

            if not match:
                header_lines.append(
                    (line_number, line)
                )
                continue

            book_name = match.group(1).strip()
            chapter_number = int(match.group(2))
            verse_number = int(match.group(3))
            text = (match.group(4) or "").strip()

            if book_name not in book_positions:
                book_order.append(book_name)
                book_positions[book_name] = len(book_order)

            position = book_positions[book_name]

            key = (
                position,
                chapter_number,
                verse_number,
            )

            if (
                key in source_keys
                or key in empty_references
            ):
                duplicates.append(
                    f"{book_name} "
                    f"{chapter_number}:{verse_number}"
                )
                continue

            if not text:
                empty_references.add(key)
                continue

            source_keys.add(key)
            source_rows.append((key, text))

        errors = []

        if len(book_order) != 66:
            errors.append(
                f"Expected 66 books, found {len(book_order)}"
            )

        if len(header_lines) != 3:
            errors.append(
                f"Expected 3 non-reference header lines, "
                f"found {len(header_lines)}"
            )

            for line_number, line in header_lines[:10]:
                errors.append(
                    f"Unparsed line {line_number}: {line!r}"
                )

        if duplicates:
            errors.append(
                f"Duplicate references: {len(duplicates)}"
            )

        if empty_references != OMITTED_VERSES:
            unexpected_empty = (
                empty_references - OMITTED_VERSES
            )
            missing_placeholders = (
                OMITTED_VERSES - empty_references
            )

            errors.append(
                "Empty-reference placeholders differ from "
                f"expected omissions. Unexpected: "
                f"{sorted(unexpected_empty)}; missing: "
                f"{sorted(missing_placeholders)}"
            )

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
        missing_keys = canonical_keys - source_keys
        extra_keys = source_keys - canonical_keys

        unexpected_missing = (
            missing_keys - OMITTED_VERSES
        )
        unexpected_present = (
            OMITTED_VERSES & source_keys
        )

        if unexpected_missing:
            errors.append(
                "Unexpected missing references: "
                + ", ".join(
                    f"{position}:{chapter}:{verse}"
                    for position, chapter, verse
                    in sorted(unexpected_missing)[:30]
                )
            )

        if unexpected_present:
            errors.append(
                "Expected omitted references were present: "
                + ", ".join(
                    f"{position}:{chapter}:{verse}"
                    for position, chapter, verse
                    in sorted(unexpected_present)
                )
            )

        if extra_keys:
            errors.append(
                "References not found in canonical database: "
                + ", ".join(
                    f"{position}:{chapter}:{verse}"
                    for position, chapter, verse
                    in sorted(extra_keys)[:30]
                )
            )

        chapter_count = len({
            (position, chapter)
            for position, chapter, _verse in source_keys
        })

        if chapter_count != 1189:
            errors.append(
                f"Expected 1189 chapters, "
                f"found {chapter_count}"
            )

        if len(source_rows) != 31086:
            errors.append(
                f"Expected 31086 verses, "
                f"found {len(source_rows)}"
            )

        if missing_keys != OMITTED_VERSES:
            errors.append(
                f"Expected {len(OMITTED_VERSES)} omitted "
                f"verse positions, found {len(missing_keys)}"
            )

        if errors:
            raise CommandError(
                "BAB validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="BAB",
                    defaults={
                        "name": "Berean Annotated Bible",
                        "language": "English",
                    },
                )
            )

            version.name = "Berean Annotated Bible"
            version.language = "English"
            version.pdf_filename = "BAB.pdf"
            version.description = (
                "Berean Annotated Bible draft, including "
                "emphasis, original-language names, literal "
                "translations, alternate readings, measurements "
                "and cross-references."
            )

            version.save(
                update_fields=[
                    "name",
                    "language",
                    "pdf_filename",
                    "description",
                ]
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse=canonical[key],
                        text=text,
                    )
                    for key, text in source_rows
                ],
                batch_size=2000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: "
                f"{version.name} ({version.abbreviation})"
            )
        )
        self.stdout.write(f"Books: {len(book_order)}")
        self.stdout.write(f"Chapters: {chapter_count}")
        self.stdout.write(
            f"Verses: {len(source_rows)}"
        )
        self.stdout.write(
            f"Empty verse positions: {len(missing_keys)}"
        )
        self.stdout.write(
            f"Ignored header lines: {len(header_lines)}"
        )
        self.stdout.write(
            f"Ignored blank lines: {blank_lines}"
        )
