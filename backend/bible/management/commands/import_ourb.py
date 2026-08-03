import html
import re
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


EXPECTED_BOOKS = {
    1, 2, 3, 4, 5,
    19, 20, 23,
    40, 41, 42, 43,
}

EXPECTED_ROWS = 14299
EXPECTED_CHAPTERS = 523
EXPECTED_ABBREVIATION = "OURB"
EXPECTED_DESCRIPTION = "One Unity Resource Bible"


def clean_resource_text(text):
    # Remove display tags but retain headings, notes,
    # references, and Scripture content.
    text = re.sub(
        r"<[^>]*>",
        " ",
        text,
    )

    # Remove USFM character controls while retaining
    # the text enclosed by those controls.
    text = re.sub(
        r"\\[+A-Za-z0-9-]+\*?",
        " ",
        text,
    )

    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def read_source(path):
    uri = f"file:{path.resolve()}?mode=ro"

    database = sqlite3.connect(uri, uri=True)
    database.row_factory = sqlite3.Row

    try:
        integrity = database.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise CommandError(
                "Source integrity check failed: "
                f"{integrity}"
            )

        details = database.execute(
            """
            SELECT *
            FROM Details
            LIMIT 1
            """
        ).fetchone()

        rows = database.execute(
            """
            SELECT Book, Chapter, Verse, Scripture
            FROM Bible
            ORDER BY Book, Chapter, Verse
            """
        ).fetchall()
    finally:
        database.close()

    if details is None:
        raise CommandError(
            "The Details record is missing"
        )

    return dict(details), rows


class Command(BaseCommand):
    help = (
        "Import the partial One Unity Resource Bible "
        "from its MyBible SQLite module."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            type=str,
            help="Path to ourb.mybible",
        )

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(
                f"MyBible source not found: {path}"
            )

        pdf_path = path.parent / "ourb.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        details, rows = read_source(path)

        if (
            details.get("Abbreviation")
            != EXPECTED_ABBREVIATION
        ):
            raise CommandError(
                "Unexpected source abbreviation: "
                f"{details.get('Abbreviation')!r}"
            )

        if (
            details.get("Description")
            != EXPECTED_DESCRIPTION
        ):
            raise CommandError(
                "Unexpected source description: "
                f"{details.get('Description')!r}"
            )

        if len(rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} rows, "
                f"found {len(rows)}"
            )

        source = {}

        for row in rows:
            key = (
                int(row["Book"]),
                int(row["Chapter"]),
                int(row["Verse"]),
            )

            if key in source:
                raise CommandError(
                    f"Duplicate source position: {key}"
                )

            text = clean_resource_text(
                row["Scripture"] or ""
            )

            if not text:
                raise CommandError(
                    f"Empty cleaned text at {key}"
                )

            if "\ufffd" in text:
                raise CommandError(
                    "Replacement character found at "
                    f"{key}"
                )

            if re.search(
                r"<[^>]+>|\\[+A-Za-z]",
                text,
            ):
                raise CommandError(
                    "Formatting marker remains at "
                    f"{key}: {text[:200]!r}"
                )

            source[key] = text

        represented_books = {
            book
            for book, chapter, verse in source
        }

        if represented_books != EXPECTED_BOOKS:
            raise CommandError(
                "Book coverage differs from expected. "
                f"Found: {sorted(represented_books)}"
            )

        source_chapters = {
            (book, chapter)
            for book, chapter, verse in source
        }

        if len(source_chapters) != EXPECTED_CHAPTERS:
            raise CommandError(
                f"Expected {EXPECTED_CHAPTERS} chapters, "
                f"found {len(source_chapters)}"
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
            if (
                verse.chapter.book.position
                in EXPECTED_BOOKS
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

        if len(canonical) != EXPECTED_ROWS:
            raise CommandError(
                "Expected 14299 canonical positions "
                "for the represented books, found "
                f"{len(canonical)}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="OURB",
                    defaults={
                        "name": (
                            "One Unity Resource Bible"
                        ),
                        "language": "English",
                        "year": 2016,
                        "description": (
                            "Partial One Unity Resource "
                            "Bible comprising Genesis–"
                            "Deuteronomy, Psalms, Proverbs, "
                            "Isaiah, and the four Gospels. "
                            "Translated and compiled by "
                            "Thomas Robinson. Copyright "
                            "© 2016 Thomas Robinson; "
                            "licensed under CC BY-SA 4.0."
                        ),
                        "pdf_filename": "ourb.pdf",
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
                batch_size=1000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})"
            )
        )
        self.stdout.write("Books: 12")
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Source rows: {len(rows)}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            "Formatting tags removed; "
            "resource notes retained"
        )
