import html
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
    "தேவனின் எபிரேயப் பெயர்கள் பதிப்பு - "
    "Hebrew Names OF God Version in Tamil"
)
EXPECTED_ABBREVIATION = "THNGV"
EXPECTED_ROWS = 31102
EXPECTED_CHAPTERS = 1189
ALLOWED_SCRIPTURE_TAGS = {"font"}


def clean_scripture(value):
    text = html.unescape(value or "")

    tag_names = {
        tag.casefold()
        for tag in re.findall(
            r"</?\s*([A-Za-z0-9]+)\b[^>]*>",
            text,
        )
    }

    unexpected_tags = (
        tag_names - ALLOWED_SCRIPTURE_TAGS
    )

    if unexpected_tags:
        raise CommandError(
            "Unexpected scripture HTML tags: "
            + ", ".join(sorted(unexpected_tags))
        )

    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class Command(BaseCommand):
    help = (
        "Import the Hebrew Names of God Version "
        "in Tamil from a MyBible SQLite module."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help="Path to THNGV.mybible",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: {source_path}"
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
                row["name"].casefold()
                for row in source_database.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            missing_tables = (
                {"bible", "details"} - table_names
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

            comments = details["Comments"] or ""

            if "Public Domain" not in comments:
                raise CommandError(
                    "Source is not marked Public Domain."
                )

            if (
                "விற்பனை செய்ய அனுமதி இல்லை"
                not in comments
            ):
                raise CommandError(
                    "Expected no-sale license wording "
                    "was not found."
                )

            if details["Language"] != "ta":
                raise CommandError(
                    "Unexpected source language: "
                    f"{details['Language']!r}"
                )

            if details["OT"] != 1 or details["NT"] != 1:
                raise CommandError(
                    "Expected a complete OT and NT source."
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

        if len(source_rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} rows, "
                f"found {len(source_rows)}"
            )

        source = {}
        source_chapters = set()
        formatted_rows = 0

        for row_number, row in enumerate(
            source_rows,
            start=1,
        ):
            key = (
                row["Book"],
                row["Chapter"],
                row["Verse"],
            )
            raw_text = row["Scripture"] or ""

            if key in source:
                raise CommandError(
                    f"Duplicate source position: {key}"
                )

            if re.search(r"<[^>]+>", raw_text):
                formatted_rows += 1

            text = clean_scripture(raw_text)

            if not text:
                raise CommandError(
                    "Blank cleaned text at "
                    f"{key} (source row {row_number})"
                )

            if "\ufffd" in text:
                raise CommandError(
                    "Replacement character at "
                    f"{key}"
                )

            if re.search(r"<[^>]+>", text):
                raise CommandError(
                    "Formatting marker remains at "
                    f"{key}"
                )

            source[key] = text
            source_chapters.add(
                (key[0], key[1])
            )

        if len(source_chapters) != EXPECTED_CHAPTERS:
            raise CommandError(
                f"Expected {EXPECTED_CHAPTERS} chapters, "
                f"found {len(source_chapters)}"
            )

        if len({key[0] for key in source}) != 66:
            raise CommandError(
                "Expected 66 represented books."
            )

        canonical_verses = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.select_related(
                "chapter__book",
            )
        }

        if len(canonical_verses) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} canonical "
                "positions, found "
                f"{len(canonical_verses)}"
            )

        missing = (
            set(canonical_verses) - set(source)
        )
        extra = (
            set(source) - set(canonical_verses)
        )

        if missing or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {sorted(missing)[:20]}; "
                f"extra: {sorted(extra)[:20]}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="THNGV",
                    defaults={
                        "name": (
                            "Hebrew Names of God "
                            "Version in Tamil"
                        ),
                        "language": "Tamil",
                        "year": 2026,
                    },
                )
            )

            version.name = (
                "Hebrew Names of God Version in Tamil"
            )
            version.language = "Tamil"
            version.year = 2026
            version.description = (
                "Hebrew Names of God Version in "
                "Tamil, restored and edited by "
                "Pastor Paul Jonathan and based on "
                "the 1871 Henry Bower Tamil Bible. "
                "Published in 2026 by Pastor Paul "
                "Jonathan and the Word of God Team; "
                "digital module created by Yesudas "
                "Solomon. Public Domain; free "
                "unchanged copying, sharing, and "
                "distribution are permitted; sale "
                "is prohibited."
            )
            version.pdf_filename = ""
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
        self.stdout.write("Language: Tamil")
        self.stdout.write("Books: 66")
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Source rows: {len(source)}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Formatting-tag rows cleaned: "
            f"{formatted_rows}"
        )
        self.stdout.write(
            "Hebrew names and textual notes retained"
        )
        self.stdout.write(
            "PDF: not configured"
        )
