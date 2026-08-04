import re
import sqlite3
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Verse,
    VerseText,
)


EXPECTED_TITLE = (
    "புதிய ஏற்பாடு 1836 இரேனியஸ் ஐயர் - "
    "Tamil New Testament 1836 by C.T.E. Rhenius"
)
EXPECTED_ABBREVIATION = "TRHE1836"
EXPECTED_SOURCE_ROWS = 7957
EXPECTED_IMPORTED_ROWS = 7950

EXPECTED_PLACEHOLDERS = {
    (40, 9, 38): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (43, 6, 71): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (43, 21, 25): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (44, 10, 48): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (44, 13, 52): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (44, 14, 28): (
        "[வசனம் இல்லை, மேலே அல்லது கீழே "
        "உள்ள வசனத்தில் பார்க்கவும்]"
    ),
    (65, 1, 25): (
        "[வசனம் இல்லை, மேலே உள்ள "
        "வசனத்தில் பார்க்கவும்]"
    ),
}


def normalize_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


class Command(BaseCommand):
    help = (
        "Import the public-domain 1836 Rhenius "
        "Tamil New Testament from a MyBible file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help="Path to TRHE1836.mybible",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: {source_path}"
            )

        pdf_path = (
            source_path.parent / "TRHE1836.pdf"
        )

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        uri = (
            f"file:{source_path.resolve()}?mode=ro"
        )

        try:
            source_database = sqlite3.connect(
                uri,
                uri=True,
            )
            source_database.row_factory = sqlite3.Row
        except sqlite3.Error as error:
            raise CommandError(
                f"Unable to open source database: {error}"
            ) from error

        try:
            integrity = source_database.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if integrity != "ok":
                raise CommandError(
                    "Source integrity check failed: "
                    f"{integrity}"
                )

            table_names = {
                row["name"]
                for row in source_database.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            missing_tables = (
                {"Bible", "Details"} - table_names
            )

            if missing_tables:
                raise CommandError(
                    "Missing source tables: "
                    + ", ".join(sorted(missing_tables))
                )

            details = source_database.execute(
                """
                SELECT
                    Title,
                    Abbreviation,
                    Comments,
                    Version,
                    VersionDate,
                    PublishDate,
                    Publisher,
                    Author,
                    Creator,
                    Source,
                    Language,
                    OT,
                    NT
                FROM Details
                LIMIT 1
                """
            ).fetchone()

            if details is None:
                raise CommandError(
                    "Source metadata is missing."
                )

            if details["Title"] != EXPECTED_TITLE:
                raise CommandError(
                    "Unexpected source title: "
                    f"{details['Title']!r}"
                )

            if (
                details["Abbreviation"]
                != EXPECTED_ABBREVIATION
            ):
                raise CommandError(
                    "Unexpected abbreviation: "
                    f"{details['Abbreviation']!r}"
                )

            if details["Comments"] != "Public Domain":
                raise CommandError(
                    "Source is not marked Public Domain."
                )

            if details["Language"] != "ta":
                raise CommandError(
                    "Unexpected source language: "
                    f"{details['Language']!r}"
                )

            if details["OT"] != 0 or details["NT"] != 1:
                raise CommandError(
                    "Expected an NT-only source."
                )

            source_rows = source_database.execute(
                """
                SELECT
                    Book,
                    Chapter,
                    Verse,
                    Scripture
                FROM Bible
                ORDER BY Book, Chapter, Verse
                """
            ).fetchall()
        except sqlite3.Error as error:
            raise CommandError(
                f"Unable to read source database: {error}"
            ) from error
        finally:
            source_database.close()

        if len(source_rows) != EXPECTED_SOURCE_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_SOURCE_ROWS} rows, "
                f"found {len(source_rows)}"
            )

        source = {}
        source_chapters = set()

        for row_number, row in enumerate(
            source_rows,
            start=1,
        ):
            key = (
                row["Book"],
                row["Chapter"],
                row["Verse"],
            )
            text = normalize_text(row["Scripture"])

            if key in source:
                raise CommandError(
                    f"Duplicate source position: {key}"
                )

            if not text:
                raise CommandError(
                    "Blank source text at "
                    f"{key} (row {row_number})"
                )

            if "\ufffd" in text:
                raise CommandError(
                    "Replacement character at "
                    f"{key}"
                )

            if re.search(r"<[^>]+>", text):
                raise CommandError(
                    f"Unexpected markup at {key}"
                )

            source[key] = text
            source_chapters.add(
                (key[0], key[1])
            )

        if len(source_chapters) != 260:
            raise CommandError(
                "Expected 260 source chapters, "
                f"found {len(source_chapters)}"
            )

        actual_placeholders = {
            key: text
            for key, text in source.items()
            if text.startswith("[வசனம் இல்லை")
        }

        if actual_placeholders != EXPECTED_PLACEHOLDERS:
            raise CommandError(
                "Placeholder validation failed. "
                f"Found: {actual_placeholders}"
            )

        canonical_verses = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.filter(
                chapter__book__position__gte=40,
            ).select_related(
                "chapter__book",
            )
        }

        if len(canonical_verses) != 7957:
            raise CommandError(
                "Expected 7957 canonical NT positions, "
                f"found {len(canonical_verses)}"
            )

        missing = (
            set(canonical_verses) - set(source)
        )
        extra = (
            set(source) - set(canonical_verses)
        )

        if missing or extra:
            raise CommandError(
                "Canonical position validation failed. "
                f"Missing: {sorted(missing)[:20]}; "
                f"extra: {sorted(extra)[:20]}"
            )

        validated_source = {
            key: text
            for key, text in source.items()
            if key not in EXPECTED_PLACEHOLDERS
        }

        if (
            len(validated_source)
            != EXPECTED_IMPORTED_ROWS
        ):
            raise CommandError(
                f"Expected {EXPECTED_IMPORTED_ROWS} "
                "importable texts, found "
                f"{len(validated_source)}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="TRHE1836",
                    defaults={
                        "name": (
                            "Rhenius Tamil "
                            "New Testament (1836)"
                        ),
                        "language": "Tamil",
                        "year": 1836,
                    },
                )
            )

            version.name = (
                "Rhenius Tamil New Testament (1836)"
            )
            version.language = "Tamil"
            version.year = 1836
            version.description = (
                "Public-domain Tamil New Testament "
                "translated by C. T. E. Rhenius and "
                "published in 1836 by The Madras "
                "Auxiliary Bible Society, printed at "
                "The Church Mission Press. Digital "
                "edition prepared and verified by "
                "Yesudas Solomon and Madanraj Joshua; "
                "distributed by Bible Minutes and "
                "WordOfGod.in."
            )
            version.pdf_filename = "TRHE1836.pdf"
            version.save()

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            verse_texts = [
                VerseText(
                    bible_version=version,
                    verse=canonical_verses[key],
                    text=text,
                )
                for key, text in validated_source.items()
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
        self.stdout.write("Language: Tamil")
        self.stdout.write("Books: 27")
        self.stdout.write("Chapters: 260")
        self.stdout.write(
            f"Source rows: {len(source)}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            "Merged-text placeholder positions "
            f"omitted: {len(EXPECTED_PLACEHOLDERS)}"
        )
        self.stdout.write(
            f"PDF: {version.pdf_filename}"
        )
