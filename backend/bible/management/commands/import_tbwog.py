import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Book,
    Verse,
    VerseText,
)


VERSION_DEFAULTS = {
    "name": (
        "Tamil Bible "
        "(Word of God Ministries)"
    ),
    "language": "Tamil",
    "year": 2016,
    "pdf_filename": "",
    "description": (
        "Tamil Bible Unicode Version, "
        "version 3.0, made available by "
        "Yesudas Solomon, founder and member "
        "of the Word of God Team, a branch of "
        "Word of God Ministries. The source "
        "module authorizes its use free of cost "
        "for non-profit purposes and states that "
        "it is available for free Bible software "
        "and free Android and iOS applications. "
        "Source: http://www.wordofgod.in. "
        "This import preserves the source verse "
        "text unchanged. No PDF is configured "
        "because the separately obtained PDF and "
        "BSI-labelled XML do not have verified "
        "provenance linking them to this module."
    ),
}

EXPECTED_ROWS = 31102
EXPECTED_BOOKS = 66


def open_read_only(path):
    header = path.read_bytes()[:16]

    if header != b"SQLite format 3\x00":
        raise CommandError(
            f"Not a SQLite database: {path}"
        )

    uri = f"{path.resolve().as_uri()}?mode=ro"

    connection = sqlite3.connect(
        uri,
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    return connection


def read_source(path):
    connection = open_read_only(path)

    try:
        quick_check = connection.execute(
            "PRAGMA quick_check"
        ).fetchone()[0]

        if quick_check != "ok":
            raise CommandError(
                "Source SQLite quick_check failed: "
                f"{quick_check}"
            )

        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        required_tables = {
            "Bible",
            "Details",
            "books",
        }

        missing_tables = (
            required_tables - tables
        )

        if missing_tables:
            raise CommandError(
                "Missing source tables: "
                + ", ".join(
                    sorted(missing_tables)
                )
            )

        details = connection.execute(
            "SELECT * FROM Details"
        ).fetchone()

        if details is None:
            raise CommandError(
                "The Details table is empty."
            )

        books = list(
            connection.execute(
                """
                SELECT book, name
                FROM books
                ORDER BY book
                """
            )
        )

        rows = list(
            connection.execute(
                """
                SELECT
                    Book,
                    Chapter,
                    Verse,
                    Scripture
                FROM Bible
                ORDER BY
                    Book,
                    Chapter,
                    Verse
                """
            )
        )
    finally:
        connection.close()

    return details, books, rows


def validate_metadata(details):
    title = (details["Title"] or "").strip()
    creator = (
        details["Creator"] or ""
    ).strip()
    publisher = (
        details["Publisher"] or ""
    ).strip()
    comments = (
        details["Comments"] or ""
    )

    required_fragments = (
        "Tamil Bible",
        "Yesudas Solomon",
        "Word of God",
        "Free of Cost",
        "Non-Profitable",
        "Free Apps",
    )

    combined = " ".join(
        (
            title,
            creator,
            publisher,
            comments,
        )
    )

    missing = [
        fragment
        for fragment in required_fragments
        if fragment.casefold()
        not in combined.casefold()
    ]

    if missing:
        raise CommandError(
            "Source metadata is missing expected "
            "identity or permission text: "
            + ", ".join(missing)
        )


def validate_books(books):
    numbers = [
        row["book"]
        for row in books
    ]

    if len(books) != EXPECTED_BOOKS:
        raise CommandError(
            "Expected 66 source books, found "
            f"{len(books)}."
        )

    if numbers != list(range(1, 67)):
        raise CommandError(
            "Source book numbering is not 1-66."
        )


def validate_rows(rows, canonical_positions):
    if len(rows) != EXPECTED_ROWS:
        raise CommandError(
            "Expected 31,102 source rows, found "
            f"{len(rows):,}."
        )

    counts = Counter(
        (
            row["Book"],
            row["Chapter"],
            row["Verse"],
        )
        for row in rows
    )

    duplicates = sorted(
        position
        for position, count in counts.items()
        if count > 1
    )

    if duplicates:
        raise CommandError(
            "Duplicate source positions found: "
            f"{duplicates[:20]}"
        )

    source_positions = set(counts)

    missing = sorted(
        canonical_positions
        - source_positions
    )

    extra = sorted(
        source_positions
        - canonical_positions
    )

    if missing:
        raise CommandError(
            "Missing canonical positions: "
            f"{missing[:20]}"
        )

    if extra:
        raise CommandError(
            "Extra source positions: "
            f"{extra[:20]}"
        )

    blank = []
    replacement = []
    html = []
    non_nfc = []

    for row in rows:
        position = (
            row["Book"],
            row["Chapter"],
            row["Verse"],
        )

        text = row["Scripture"]

        if not isinstance(text, str):
            blank.append(position)
            continue

        if not text.strip():
            blank.append(position)

        if "\ufffd" in text:
            replacement.append(position)

        if re.search(r"<[^>]+>", text):
            html.append(position)

        if unicodedata.normalize(
            "NFC",
            text,
        ) != text:
            non_nfc.append(position)

    problems = {
        "blank": blank,
        "replacement": replacement,
        "HTML": html,
        "non-NFC": non_nfc,
    }

    for label, positions in problems.items():
        if positions:
            raise CommandError(
                f"Source contains {label} texts: "
                f"{positions[:20]}"
            )


class Command(BaseCommand):
    help = (
        "Import the Word of God Ministries "
        "Tamil Bible from its MyBible module."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            default="data/TBWOG.mybible",
            help=(
                "Path to the Word of God "
                "Ministries MyBible module."
            ),
        )

    def handle(self, *args, **options):
        source_path = Path(
            options["source"]
        )

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: "
                f"{source_path}"
            )

        details, source_books, rows = (
            read_source(source_path)
        )

        validate_metadata(details)
        validate_books(source_books)

        canonical_rows = list(
            Verse.objects.values_list(
                "chapter__book__position",
                "chapter__number",
                "number",
                "id",
            )
        )

        canonical_positions = {
            (
                book_position,
                chapter_number,
                verse_number,
            )
            for (
                book_position,
                chapter_number,
                verse_number,
                verse_id,
            ) in canonical_rows
        }

        if len(canonical_positions) != (
            EXPECTED_ROWS
        ):
            raise CommandError(
                "The Django canonical database "
                "must contain exactly 31,102 "
                "positions; found "
                f"{len(canonical_positions):,}."
            )

        validate_rows(
            rows,
            canonical_positions,
        )

        verse_ids = {
            (
                book_position,
                chapter_number,
                verse_number,
            ): verse_id
            for (
                book_position,
                chapter_number,
                verse_number,
                verse_id,
            ) in canonical_rows
        }

        source_texts = {
            (
                row["Book"],
                row["Chapter"],
                row["Verse"],
            ): row["Scripture"]
            for row in rows
        }

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="TBWOG",
                    defaults=VERSION_DEFAULTS,
                )
            )

            VerseText.objects.filter(
                bible_version=version,
            ).delete()

            objects = [
                VerseText(
                    bible_version_id=version.id,
                    verse_id=verse_ids[position],
                    text=source_texts[position],
                )
                for position in sorted(
                    source_texts
                )
            ]

            VerseText.objects.bulk_create(
                objects,
                batch_size=1000,
            )

        imported_count = (
            VerseText.objects.filter(
                bible_version=version,
            ).count()
        )

        if imported_count != EXPECTED_ROWS:
            raise CommandError(
                "Post-import count mismatch: "
                f"{imported_count:,}"
            )

        book_count = Book.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                (
                    "Created"
                    if created
                    else "Updated"
                )
                + ": "
                + version.name
                + " (TBWOG)"
            )
        )
        self.stdout.write(
            "Language: Tamil"
        )
        self.stdout.write(
            "Year: 2016"
        )
        self.stdout.write(
            f"Canonical books available: "
            f"{book_count}"
        )
        self.stdout.write(
            "Canonical positions: 31102"
        )
        self.stdout.write(
            "Imported verse texts: 31102"
        )
        self.stdout.write(
            "Source format: MyBible SQLite"
        )
        self.stdout.write(
            "Source module version: "
            f"{details['Version']}"
        )
        self.stdout.write(
            "Creator: Yesudas Solomon"
        )
        self.stdout.write(
            "Publisher: Word of God Ministries"
        )
        self.stdout.write(
            "Use terms: free of cost and "
            "non-profit purposes; free apps"
        )
        self.stdout.write(
            "Scripture text: unchanged"
        )
        self.stdout.write(
            "PDF: not configured"
        )
