import html
import re
import sqlite3
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


VERSION_NAME = "Jubilee Bible 2000"
ABBREVIATION = "JUB"
LANGUAGE = "English"
YEAR = 2000

DESCRIPTION = (
    "The Jubilee Bible 2000 (JUB), translated and "
    "edited by Russell M. Stendal. The published JUB "
    "notice states that it may be used freely in "
    "nonprofit, noncommercial Bible distribution "
    "endeavors provided the content is not altered. "
    "This import preserves the source Scripture wording. "
    "Presentation-only red-letter tags are removed and "
    "stored character entities are decoded for display. "
    "One verified source-module indexing defect is "
    "corrected: John 4:50 was stored at Zechariah 4:50. "
    "The verse wording itself is unchanged. No PDF is "
    "configured because the local JUB.pdf is only a "
    "locally generated Genesis 1 sample, not a complete "
    "publisher-issued JUB PDF."
)

EXPECTED_JOHN_4_50 = (
    "Jesus said unto him, Go; thy son lives. "
    "And the man believed the word that Jesus "
    "spoke unto him, and he went."
)

TAG_PATTERN = re.compile(
    r"</?([A-Za-z][A-Za-z0-9]*)"
    r"(?:\s[^>]*)?/?>"
)

PRESENTATION_PATTERN = re.compile(
    r"</?J>",
    flags=re.IGNORECASE,
)


def clean_text(text):
    if not isinstance(text, str):
        return ""

    # J marks red-letter presentation only.
    without_presentation = (
        PRESENTATION_PATTERN.sub("", text)
    )

    # Decode stored entities such as
    # &lt;&lt;A Psalm of David.&gt;&gt;.
    return html.unescape(
        without_presentation
    ).strip()


def open_source(path):
    try:
        source = sqlite3.connect(
            path.resolve().as_uri()
            + "?mode=ro&immutable=1",
            uri=True,
        )
    except sqlite3.Error as error:
        raise CommandError(
            f"Could not open source SQLite module: "
            f"{error}"
        ) from error

    source.execute(
        "PRAGMA query_only = ON"
    )

    quick_check = source.execute(
        "PRAGMA quick_check"
    ).fetchone()[0]

    if quick_check != "ok":
        source.close()

        raise CommandError(
            "Source SQLite quick_check failed: "
            f"{quick_check}"
        )

    return source


def validate_schema(source):
    tables = {
        row[0]
        for row in source.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        )
    }

    required_tables = {
        "books",
        "info",
        "verses",
    }

    missing_tables = (
        required_tables
        - tables
    )

    if missing_tables:
        raise CommandError(
            "Missing source tables: "
            + repr(
                sorted(missing_tables)
            )
        )

    book_columns = {
        row[1]
        for row in source.execute(
            "PRAGMA table_info(books)"
        )
    }

    verse_columns = {
        row[1]
        for row in source.execute(
            "PRAGMA table_info(verses)"
        )
    }

    required_book_columns = {
        "book_number",
        "short_name",
        "long_name",
    }

    required_verse_columns = {
        "book_number",
        "chapter",
        "verse",
        "text",
    }

    if not (
        required_book_columns
        <= book_columns
    ):
        raise CommandError(
            "Unexpected books schema: "
            + repr(
                sorted(book_columns)
            )
        )

    if not (
        required_verse_columns
        <= verse_columns
    ):
        raise CommandError(
            "Unexpected verses schema: "
            + repr(
                sorted(verse_columns)
            )
        )


def validate_metadata(source):
    metadata = dict(
        source.execute(
            """
            SELECT name, value
            FROM info
            """
        ).fetchall()
    )

    description = (
        metadata.get(
            "description",
            "",
        ).strip()
    )

    language = (
        metadata.get(
            "language",
            "",
        ).strip()
    )

    strong_numbers = (
        metadata.get(
            "strong_numbers",
            "",
        ).strip().casefold()
    )

    if (
        description
        != "English Jubilee 2000 Bible"
    ):
        raise CommandError(
            "Unexpected source description: "
            f"{description!r}"
        )

    if language != "en":
        raise CommandError(
            "Unexpected source language: "
            f"{language!r}"
        )

    if strong_numbers != "false":
        raise CommandError(
            "Unexpected Strong-number setting: "
            f"{strong_numbers!r}"
        )

    return metadata


def parse_source(source):
    source_books = source.execute(
        """
        SELECT
            book_number,
            short_name,
            long_name
        FROM books
        ORDER BY book_number
        """
    ).fetchall()

    if len(source_books) != 66:
        raise CommandError(
            "Expected 66 source books; "
            f"found {len(source_books)}"
        )

    book_number_to_position = {
        book_number: position
        for position, (
            book_number,
            _,
            _,
        ) in enumerate(
            source_books,
            start=1,
        )
    }

    rows = source.execute(
        """
        SELECT
            book_number,
            chapter,
            verse,
            text
        FROM verses
        ORDER BY
            book_number,
            chapter,
            verse
        """
    ).fetchall()

    parsed = {}
    raw_tag_counts = Counter()
    correction_count = 0

    for (
        book_number,
        chapter_number,
        verse_number,
        raw_text,
    ) in rows:
        position = (
            book_number_to_position.get(
                book_number
            )
        )

        if position is None:
            raise CommandError(
                "Unknown source book number: "
                f"{book_number}"
            )

        chapter_number = int(
            chapter_number
        )

        verse_number = int(
            verse_number
        )

        tags = [
            match.group(1).casefold()
            for match in TAG_PATTERN.finditer(
                raw_text
                if isinstance(raw_text, str)
                else ""
            )
        ]

        raw_tag_counts.update(tags)

        unexpected_tags = {
            tag
            for tag in tags
            if tag != "j"
        }

        if unexpected_tags:
            raise CommandError(
                "Unexpected presentation tags: "
                + repr(
                    sorted(unexpected_tags)
                )
            )

        text = clean_text(raw_text)

        if not text:
            raise CommandError(
                "Blank Scripture text at "
                f"module position "
                f"{book_number}:"
                f"{chapter_number}:"
                f"{verse_number}"
            )

        if "\ufffd" in text:
            raise CommandError(
                "Replacement character at "
                f"module position "
                f"{book_number}:"
                f"{chapter_number}:"
                f"{verse_number}"
            )

        # Verified source indexing defect.
        if (
            book_number == 450
            and chapter_number == 4
            and verse_number == 50
        ):
            if text != EXPECTED_JOHN_4_50:
                raise CommandError(
                    "The correction candidate "
                    "does not match the verified "
                    "JUB John 4:50 wording."
                )

            position = 43
            correction_count += 1

        key = (
            position,
            chapter_number,
            verse_number,
        )

        if key in parsed:
            raise CommandError(
                "Duplicate canonical position "
                f"after correction: {key}"
            )

        parsed[key] = text

    if correction_count != 1:
        raise CommandError(
            "Expected exactly one verified "
            "John 4:50 correction; found "
            f"{correction_count}"
        )

    if len(rows) != 31102:
        raise CommandError(
            "Expected 31,102 source rows; "
            f"found {len(rows)}"
        )

    return (
        parsed,
        source_books,
        raw_tag_counts,
        correction_count,
    )


class Command(BaseCommand):
    help = (
        "Import the Jubilee Bible 2000 "
        "from a MyBible SQLite module."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            default="data/JUB.SQLite3",
            help=(
                "Path to the JUB MyBible "
                "SQLite module."
            ),
        )

    def handle(self, *args, **options):
        source_path = Path(
            options["source"]
        ).resolve()

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: "
                f"{source_path}"
            )

        source = open_source(
            source_path
        )

        try:
            validate_schema(source)

            metadata = validate_metadata(
                source
            )

            (
                parsed,
                source_books,
                tag_counts,
                correction_count,
            ) = parse_source(source)
        finally:
            source.close()

        canonical_verses = list(
            Verse.objects.select_related(
                "chapter__book"
            ).order_by(
                "chapter__book__position",
                "chapter__number",
                "number",
            )
        )

        if len(canonical_verses) != 31102:
            raise CommandError(
                "Expected 31,102 canonical "
                "verses; found "
                f"{len(canonical_verses)}"
            )

        canonical_lookup = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in canonical_verses
        }

        canonical_positions = set(
            canonical_lookup
        )

        source_positions = set(
            parsed
        )

        missing = sorted(
            canonical_positions
            - source_positions
        )

        extra = sorted(
            source_positions
            - canonical_positions
        )

        if missing or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {missing[:20]}; "
                f"extra: {extra[:20]}"
            )

        verse_texts = [
            VerseText(
                verse=canonical_lookup[
                    position
                ],
                text=parsed[position],
            )
            for position in sorted(
                canonical_positions
            )
        ]

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation=ABBREVIATION,
                    defaults={
                        "name": VERSION_NAME,
                        "language": LANGUAGE,
                        "year": YEAR,
                        "description": DESCRIPTION,
                        "pdf_filename": "",
                    },
                )
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            for verse_text in verse_texts:
                verse_text.bible_version = (
                    version
                )

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=2000,
            )

        action = (
            "Created"
            if created
            else "Updated"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: "
                f"{version.name} "
                f"({version.abbreviation})"
            )
        )

        self.stdout.write(
            f"Language: {version.language}"
        )
        self.stdout.write(
            f"Year: {version.year}"
        )
        self.stdout.write(
            "Canonical books available: "
            f"{Book.objects.count()}"
        )
        self.stdout.write(
            "Canonical positions: "
            f"{len(canonical_positions)}"
        )
        self.stdout.write(
            "Imported verse texts: "
            f"{len(verse_texts)}"
        )
        self.stdout.write(
            "Source format: MyBible SQLite"
        )
        self.stdout.write(
            "Source description: "
            f"{metadata['description']}"
        )
        self.stdout.write(
            "Presentation tags removed: "
            f"{tag_counts.get('j', 0)}"
        )
        self.stdout.write(
            "Verified indexing corrections: "
            f"{correction_count}"
        )
        self.stdout.write(
            "Scripture wording: unchanged"
        )
        self.stdout.write(
            "PDF: not configured"
        )
