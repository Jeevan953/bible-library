import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


EXPECTED_NAME = "இண்டியன் ரிவைஸ்டு வெர்ஸன்"
EXPECTED_MODULE = "ta_irv"
EXPECTED_ROWS = 31103
EXPECTED_CANONICAL_POSITIONS = 31102
EXTRA_POSITION = (64, 1, 15)
MERGE_TARGET = (64, 1, 14)


def read_source(path):
    uri = f"file:{path.resolve()}?mode=ro"

    source_connection = sqlite3.connect(
        uri,
        uri=True,
    )
    source_connection.row_factory = sqlite3.Row

    try:
        integrity = source_connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise CommandError(
                f"Source integrity check failed: {integrity}"
            )

        metadata = {
            row["field"]: row["value"]
            for row in source_connection.execute(
                "SELECT field, value FROM meta"
            )
        }

        rows = source_connection.execute(
            """
            SELECT id, book, chapter, verse, text
            FROM verses
            ORDER BY id
            """
        ).fetchall()
    finally:
        source_connection.close()

    return metadata, rows


class Command(BaseCommand):
    help = (
        "Import the Tamil Indian Revised Version "
        "from its SQLite source."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            type=str,
            help="Path to irv.sqlite",
        )

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(
                f"SQLite source not found: {path}"
            )

        pdf_path = path.parent / "irv.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        metadata, rows = read_source(path)

        if metadata.get("name") != EXPECTED_NAME:
            raise CommandError(
                "Unexpected source name: "
                f"{metadata.get('name')!r}"
            )

        if metadata.get("module") != EXPECTED_MODULE:
            raise CommandError(
                "Unexpected source module: "
                f"{metadata.get('module')!r}"
            )

        if len(rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} source rows, "
                f"found {len(rows)}"
            )

        source = {}

        for row in rows:
            key = (
                int(row["book"]),
                int(row["chapter"]),
                int(row["verse"]),
            )
            text = row["text"].strip()

            if key in source:
                raise CommandError(
                    f"Duplicate source position: {key}"
                )

            if not text:
                raise CommandError(
                    f"Empty source text at {key}"
                )

            if "\ufffd" in text:
                raise CommandError(
                    "Replacement character found at "
                    f"{key}"
                )

            source[key] = text

        extra_text = source.pop(
            EXTRA_POSITION,
            None,
        )
        target_text = source.get(MERGE_TARGET)

        if not extra_text:
            raise CommandError(
                "Expected 3 John 1:15 was not found"
            )

        if not target_text:
            raise CommandError(
                "Expected 3 John 1:14 was not found"
            )

        source[MERGE_TARGET] = (
            f"{target_text} {extra_text}"
        )

        if len(source) != EXPECTED_CANONICAL_POSITIONS:
            raise CommandError(
                "Expected 31102 normalized texts, found "
                f"{len(source)}"
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

        source_keys = set(source)
        canonical_keys = set(canonical)

        missing = canonical_keys - source_keys
        extra = source_keys - canonical_keys

        if missing or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {sorted(missing)[:20]}; "
                f"extra: {sorted(extra)[:20]}"
            )

        books = {
            book
            for book, chapter, verse in source
        }
        chapters = {
            (book, chapter)
            for book, chapter, verse in source
        }

        if len(books) != 66:
            raise CommandError(
                f"Expected 66 books, found {len(books)}"
            )

        if len(chapters) != 1189:
            raise CommandError(
                "Expected 1189 chapters, found "
                f"{len(chapters)}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="IRV",
                    defaults={
                        "name": (
                            "Indian Revised Version "
                            "(Tamil)"
                        ),
                        "language": "Tamil",
                        "year": 2019,
                        "description": (
                            "Indian Revised Version Holy "
                            "Bible in Tamil, translated by "
                            "Bridge Connectivity Solutions. "
                            "Copyright © 2017, 2019 Bridge "
                            "Connectivity Solutions; "
                            "licensed under CC BY-SA 4.0."
                        ),
                        "pdf_filename": "irv.pdf",
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
                for key, text in source.items()
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
        self.stdout.write("Language: Tamil")
        self.stdout.write("Books: 66")
        self.stdout.write("Chapters: 1189")
        self.stdout.write(
            f"Source rows: {len(rows)}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            "Merged source 3 John 1:15 into "
            "canonical 3 John 1:14"
        )
