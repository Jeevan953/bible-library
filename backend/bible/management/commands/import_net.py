import html
import re
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


EXPECTED_ROWS = 31087
EXPECTED_IMPORTED = 31086

EXPECTED_MISSING = {
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


def clean_net_text(text):
    # Remove footnotes if present.
    text = re.sub(
        r"<RF\b[^>]*>.*?<Rf>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove section headings.
    text = re.sub(
        r"<TS\b[^>]*>.*?<Ts>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove remaining display controls while
    # retaining their enclosed Scripture text.
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(
        r"\\[+A-Za-z0-9-]+\*?",
        " ",
        text,
    )

    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_versification(source):
    normalized = dict(source)

    # Merge the final 3 John greeting.
    greeting = normalized.pop(
        (64, 1, 15),
        None,
    )
    verse_fourteen = normalized.get(
        (64, 1, 14)
    )

    if (
        greeting
        != (
            "Peace be with you. The friends here "
            "greet you. Greet the friends there "
            "by name."
        )
        or not verse_fourteen
    ):
        raise CommandError(
            "Unexpected 3 John versification"
        )

    normalized[(64, 1, 14)] = (
        f"{verse_fourteen} {greeting}"
    )

    # Move the dragon sentence to Revelation 13:1.
    dragon_sentence = normalized.pop(
        (66, 12, 18),
        None,
    )
    revelation_thirteen = normalized.get(
        (66, 13, 1)
    )

    if (
        dragon_sentence
        != (
            "And the dragon stood on the sand "
            "of the seashore."
        )
        or not revelation_thirteen
    ):
        raise CommandError(
            "Unexpected Revelation versification"
        )

    normalized[(66, 13, 1)] = (
        f"{dragon_sentence} {revelation_thirteen}"
    )

    # NET numbers the final 2 Corinthians greeting
    # as verses 12–13 instead of canonical 12–14.
    combined_greeting = normalized.pop(
        (47, 13, 12),
        None,
    )
    final_blessing = normalized.pop(
        (47, 13, 13),
        None,
    )

    expected_combined = (
        "Greet one another with a holy kiss. "
        "All the saints greet you."
    )

    expected_blessing = (
        "The grace of the Lord Jesus Christ "
        "and the love of God and the fellowship "
        "of the Holy Spirit be with you all."
    )

    if combined_greeting != expected_combined:
        raise CommandError(
            "Unexpected 2 Corinthians 13:12 text"
        )

    if final_blessing != expected_blessing:
        raise CommandError(
            "Unexpected 2 Corinthians 13:13 text"
        )

    normalized[(47, 13, 12)] = (
        "Greet one another with a holy kiss."
    )
    normalized[(47, 13, 13)] = (
        "All the saints greet you."
    )
    normalized[(47, 13, 14)] = final_blessing

    return normalized


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
        "Import the noteless NET Bible "
        "Second Edition from MyBible SQLite."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            type=str,
            help="Path to net.mybible",
        )

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(
                f"MyBible source not found: {path}"
            )

        details, rows = read_source(path)

        if details.get("Abbreviation") != "NET2":
            raise CommandError(
                "Unexpected abbreviation: "
                f"{details.get('Abbreviation')!r}"
            )

        if details.get("Version") != "2.0":
            raise CommandError(
                "Unexpected version: "
                f"{details.get('Version')!r}"
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

            text = clean_net_text(
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

        normalized = normalize_versification(
            source
        )

        if len(normalized) != EXPECTED_IMPORTED:
            raise CommandError(
                f"Expected {EXPECTED_IMPORTED} "
                "normalized texts, found "
                f"{len(normalized)}"
            )

        source_books = {
            book
            for book, chapter, verse in source
        }
        source_chapters = {
            (book, chapter)
            for book, chapter, verse in source
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

        normalized_keys = set(normalized)
        canonical_keys = set(canonical)

        actual_missing = (
            canonical_keys - normalized_keys
        )
        extra = normalized_keys - canonical_keys

        if actual_missing != EXPECTED_MISSING:
            raise CommandError(
                "Missing positions differ from "
                "expected. Unexpected: "
                f"{sorted(actual_missing - EXPECTED_MISSING)}; "
                "not missing: "
                f"{sorted(EXPECTED_MISSING - actual_missing)}"
            )

        if extra:
            raise CommandError(
                f"Unexpected positions: "
                f"{sorted(extra)[:20]}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="NET2",
                    defaults={
                        "name": (
                            "NET Bible "
                            "(Second Edition)"
                        ),
                        "language": "English",
                        "year": 2017,
                        "description": (
                            "NET Bible® Second Edition. "
                            "Scripture quoted by permission. "
                            "Quotations designated (NET) are "
                            "from the NET Bible® copyright "
                            "©1996–2016 by Biblical Studies "
                            "Press, L.L.C. "
                            "http://netbible.com. "
                            "All rights reserved."
                        ),
                        # PDF redistribution requires
                        # separate written permission.
                        "pdf_filename": "",
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
                for key, text in normalized.items()
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
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Missing verse positions: "
            f"{len(EXPECTED_MISSING)}"
        )
        self.stdout.write(
            "PDF: not configured "
            "(separate permission required)"
        )
