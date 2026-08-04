import re
import sqlite3
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import TamilDictionaryEntry


EXPECTED_TITLE = "Tamil Bible Dictionary"
EXPECTED_ABBREVIATION = "TAMDIC"
EXPECTED_CREATOR = "Yesudas Solomon"
EXPECTED_ROWS = 2550


def normalize_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


class Command(BaseCommand):
    help = (
        "Import the Tamil Bible Dictionary "
        "from a MyBible SQLite dictionary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help=(
                "Path to "
                "Tamil-Bible-Dictionary.dct.mybible"
            ),
        )

    def handle(self, *args, **options):
        source = Path(options["source"])

        if not source.is_file():
            raise CommandError(
                f"Dictionary file not found: {source}"
            )

        uri = f"file:{source.resolve()}?mode=ro"

        try:
            database = sqlite3.connect(
                uri,
                uri=True,
            )
            database.row_factory = sqlite3.Row
        except sqlite3.Error as error:
            raise CommandError(
                f"Unable to open dictionary: {error}"
            ) from error

        try:
            integrity = database.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if integrity != "ok":
                raise CommandError(
                    "Dictionary integrity check failed: "
                    f"{integrity}"
                )

            table_names = {
                row["name"]
                for row in database.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            required_tables = {
                "details",
                "dictionary",
            }

            missing_tables = (
                required_tables - table_names
            )

            if missing_tables:
                raise CommandError(
                    "Missing source tables: "
                    + ", ".join(sorted(missing_tables))
                )

            details = database.execute(
                """
                SELECT
                    title,
                    abbreviation,
                    version,
                    versiondate,
                    publishdate,
                    publisher,
                    creator,
                    comments
                FROM details
                LIMIT 1
                """
            ).fetchone()

            if details is None:
                raise CommandError(
                    "Dictionary metadata is missing."
                )

            if details["title"] != EXPECTED_TITLE:
                raise CommandError(
                    "Unexpected dictionary title: "
                    f"{details['title']!r}"
                )

            if (
                details["abbreviation"]
                != EXPECTED_ABBREVIATION
            ):
                raise CommandError(
                    "Unexpected abbreviation: "
                    f"{details['abbreviation']!r}"
                )

            if details["creator"] != EXPECTED_CREATOR:
                raise CommandError(
                    "Unexpected dictionary creator: "
                    f"{details['creator']!r}"
                )

            source_rows = database.execute(
                """
                SELECT word, data
                FROM dictionary
                ORDER BY word
                """
            ).fetchall()
        except sqlite3.Error as error:
            raise CommandError(
                f"Unable to read dictionary: {error}"
            ) from error
        finally:
            database.close()

        if len(source_rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Expected {EXPECTED_ROWS} entries, "
                f"found {len(source_rows)}"
            )

        entries = []
        normalized_words = set()

        for row_number, row in enumerate(
            source_rows,
            start=1,
        ):
            word = normalize_text(row["word"])
            definition = normalize_text(row["data"])

            if not word:
                raise CommandError(
                    f"Blank word at source row {row_number}"
                )

            if not definition:
                raise CommandError(
                    "Blank definition for "
                    f"{word!r}"
                )

            if len(word) > 100:
                raise CommandError(
                    f"Word exceeds 100 characters: {word!r}"
                )

            if (
                "\ufffd" in word
                or "\ufffd" in definition
            ):
                raise CommandError(
                    "Replacement character found in "
                    f"{word!r}"
                )

            if re.search(r"<[^>]+>", definition):
                raise CommandError(
                    f"HTML found in definition: {word!r}"
                )

            normalized_word = word.casefold()

            if normalized_word in normalized_words:
                raise CommandError(
                    f"Duplicate dictionary word: {word!r}"
                )

            normalized_words.add(normalized_word)

            entries.append(
                TamilDictionaryEntry(
                    word=word,
                    definition=definition,
                )
            )

        if len(entries) != EXPECTED_ROWS:
            raise CommandError(
                "Validated entry count changed "
                "unexpectedly."
            )

        with transaction.atomic():
            TamilDictionaryEntry.objects.all().delete()

            TamilDictionaryEntry.objects.bulk_create(
                entries,
                batch_size=1000,
            )

        imported_count = (
            TamilDictionaryEntry.objects.count()
        )

        if imported_count != EXPECTED_ROWS:
            raise CommandError(
                "Stored dictionary count mismatch: "
                f"{imported_count}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Imported: Tamil Bible Dictionary "
                "(TAMDIC)"
            )
        )
        self.stdout.write(
            f"Entries: {imported_count}"
        )
        self.stdout.write(
            f"Version: {details['version']}"
        )
        self.stdout.write(
            f"Published: {details['publishdate']}"
        )
        self.stdout.write(
            f"Creator: {details['creator']}"
        )
        self.stdout.write(
            f"Publisher: {details['publisher']}"
        )
        self.stdout.write(
            "Usage: Free, non-profit purposes only"
        )
