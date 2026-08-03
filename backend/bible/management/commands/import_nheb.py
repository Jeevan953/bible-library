import html
import re
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


EXPECTED_ROWS = 31102
EXPECTED_IMPORTED = 31094
EXPECTED_FOOTNOTES = 6703

EXPECTED_EMPTY = {
    (40, 17, 21),
    (40, 18, 11),
    (41, 7, 16),
    (41, 9, 44),
    (41, 9, 46),
    (42, 17, 36),
    (43, 5, 4),
    (45, 16, 24),
}


def clean_nheb_text(text):
    # Remove footnotes and cross-references completely.
    text = re.sub(
        r"<RF\b[^>]*>.*?<Rf>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove remaining display tags while retaining
    # their enclosed Scripture text.
    text = re.sub(
        r"<[^>]*>",
        " ",
        text,
    )

    # Remove USFM-style formatting controls while
    # retaining their enclosed text.
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
            SELECT rowid, Book, Chapter, Verse, Scripture
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
        "Import the New Heart English Bible "
        "from its MyBible SQLite module."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            type=str,
            help="Path to nheb.mybible",
        )

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(
                f"MyBible source not found: {path}"
            )

        pdf_path = path.parent / "nheb.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        details, rows = read_source(path)

        if details.get("Title") != (
            "New Heart English Bible"
        ):
            raise CommandError(
                "Unexpected source title: "
                f"{details.get('Title')!r}"
            )

        if details.get("Abbreviation") != "NHEB":
            raise CommandError(
                "Unexpected source abbreviation: "
                f"{details.get('Abbreviation')!r}"
            )

        if details.get("Language") != "eng":
            raise CommandError(
                "Unexpected source language: "
                f"{details.get('Language')!r}"
            )

        if len(rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} rows, "
                f"found {len(rows)}"
            )

        raw_source = {}
        cleaned_source = {}
        actual_empty = set()
        footnote_count = 0

        for row in rows:
            key = (
                int(row["Book"]),
                int(row["Chapter"]),
                int(row["Verse"]),
            )

            if key in raw_source:
                raise CommandError(
                    f"Duplicate source position: {key}"
                )

            raw_text = row["Scripture"] or ""

            footnote_count += len(
                re.findall(
                    r"<RF\b[^>]*>.*?<Rf>",
                    raw_text,
                    flags=(
                        re.IGNORECASE
                        | re.DOTALL
                    ),
                )
            )

            text = clean_nheb_text(raw_text)
            raw_source[key] = raw_text

            if not text:
                actual_empty.add(key)
                continue

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

            cleaned_source[key] = text

        if footnote_count != EXPECTED_FOOTNOTES:
            raise CommandError(
                f"Expected {EXPECTED_FOOTNOTES} "
                "footnote blocks, found "
                f"{footnote_count}"
            )

        if actual_empty != EXPECTED_EMPTY:
            raise CommandError(
                "Empty positions differ from expected. "
                "Unexpected: "
                f"{sorted(actual_empty - EXPECTED_EMPTY)}; "
                "missing: "
                f"{sorted(EXPECTED_EMPTY - actual_empty)}"
            )

        if len(cleaned_source) != EXPECTED_IMPORTED:
            raise CommandError(
                f"Expected {EXPECTED_IMPORTED} clean "
                "verse texts, found "
                f"{len(cleaned_source)}"
            )

        source_books = {
            book
            for book, chapter, verse in raw_source
        }
        source_chapters = {
            (book, chapter)
            for book, chapter, verse in raw_source
        }

        if len(source_books) != 66:
            raise CommandError(
                f"Expected 66 books, "
                f"found {len(source_books)}"
            )

        if len(source_chapters) != 1189:
            raise CommandError(
                f"Expected 1189 chapters, "
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
        }

        raw_keys = set(raw_source)
        canonical_keys = set(canonical)

        missing = canonical_keys - raw_keys
        extra = raw_keys - canonical_keys

        if missing or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {sorted(missing)[:20]}; "
                f"extra: {sorted(extra)[:20]}"
            )

        expected_clean_keys = (
            canonical_keys - EXPECTED_EMPTY
        )

        if set(cleaned_source) != expected_clean_keys:
            raise CommandError(
                "Cleaned source positions do not match "
                "the expected canonical positions"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="NHEB",
                    defaults={
                        "name": (
                            "New Heart English Bible"
                        ),
                        "language": "English",
                        "year": 2026,
                        "description": (
                            "New Heart English Bible, "
                            "edited by Wayne A. Mitchell. "
                            "Public Domain 2007–2026; "
                            "module updated June 5, 2026."
                        ),
                        "pdf_filename": "nheb.pdf",
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
                for key, text
                in cleaned_source.items()
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
            f"Source rows: {len(rows)}"
        )
        self.stdout.write(
            f"Footnote blocks removed: "
            f"{footnote_count}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Empty verse positions: "
            f"{len(EXPECTED_EMPTY)}"
        )
