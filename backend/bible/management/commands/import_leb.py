import json
import re
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


EXPECTED_VERSION = "LEB"
EXPECTED_NAME = "Lexham English Bible"
EXPECTED_LANGUAGE = "en"
EXPECTED_LICENSE = (
    "Copyrighted; Free non-commercial distribution"
)
EXPECTED_COPYRIGHT = (
    "Copyright 2010, 2012 Logos Research Systems, Inc."
)
EXPECTED_BOOKS = 66
EXPECTED_CHAPTERS = 1189
EXPECTED_POSITIONS = 31102
EXPECTED_TEXTS = 31081

ATTRIBUTION = (
    "Scripture quotations marked (LEB) are from the "
    "Lexham English Bible. Copyright 2012 Logos Bible "
    "Software. Lexham is a registered trademark of "
    "Logos Bible Software."
)

# Canonical positions intentionally omitted from the
# LEB primary text. Some are textual variants, while
# other apparent differences result from versification.
EXPECTED_BLANKS = {
    (16, 7, 68),       # Nehemiah 7:68
    (40, 17, 21),      # Matthew 17:21
    (40, 18, 11),      # Matthew 18:11
    (40, 23, 14),      # Matthew 23:14
    (41, 7, 16),       # Mark 7:16
    (41, 9, 44),       # Mark 9:44
    (41, 9, 46),       # Mark 9:46
    (41, 11, 26),      # Mark 11:26
    (41, 15, 28),      # Mark 15:28
    (42, 17, 36),      # Luke 17:36
    (42, 23, 17),      # Luke 23:17
    (43, 5, 4),        # John 5:4
    (44, 8, 37),       # Acts 8:37
    (44, 15, 34),      # Acts 15:34
    (44, 19, 41),      # Acts 19:41
    (44, 24, 7),       # Acts 24:7
    (44, 28, 29),      # Acts 28:29
    (45, 16, 25),      # Romans 16:25
    (45, 16, 26),      # Romans 16:26
    (45, 16, 27),      # Romans 16:27
    (47, 13, 14),      # 2 Corinthians 13:14
}


def normalize_text(value):
    if value is None:
        return ""

    if not isinstance(value, str):
        raise CommandError(
            "A source verse is not a string: "
            f"{value!r}"
        )

    return re.sub(r"\s+", " ", value).strip()


class Command(BaseCommand):
    help = (
        "Import the Lexham English Bible from "
        "the validated LEB JSON source."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help="Path to LEB.json",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: {source_path}"
            )

        try:
            with source_path.open(
                "r",
                encoding="utf-8-sig",
            ) as source_file:
                data = json.load(source_file)
        except (OSError, UnicodeError) as error:
            raise CommandError(
                f"Unable to read source: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise CommandError(
                f"Invalid JSON source: {error}"
            ) from error

        if not isinstance(data, dict):
            raise CommandError(
                "Expected a JSON object at the top level."
            )

        if data.get("version") != EXPECTED_VERSION:
            raise CommandError(
                "Unexpected source version: "
                f"{data.get('version')!r}"
            )

        if data.get("versionName") != EXPECTED_NAME:
            raise CommandError(
                "Unexpected version name: "
                f"{data.get('versionName')!r}"
            )

        metadata = data.get("meta")

        if not isinstance(metadata, dict):
            raise CommandError(
                "Source metadata is missing or invalid."
            )

        if metadata.get("language") != EXPECTED_LANGUAGE:
            raise CommandError(
                "Unexpected source language: "
                f"{metadata.get('language')!r}"
            )

        if metadata.get("license") != EXPECTED_LICENSE:
            raise CommandError(
                "Unexpected source license: "
                f"{metadata.get('license')!r}"
            )

        if metadata.get("copyright") != EXPECTED_COPYRIGHT:
            raise CommandError(
                "Unexpected copyright notice: "
                f"{metadata.get('copyright')!r}"
            )

        books = data.get("books")

        if not isinstance(books, dict):
            raise CommandError(
                "Source books container must be an object."
            )

        if len(books) != EXPECTED_BOOKS:
            raise CommandError(
                f"Expected {EXPECTED_BOOKS} books, "
                f"found {len(books)}"
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

        if len(canonical_verses) != EXPECTED_POSITIONS:
            raise CommandError(
                f"Expected {EXPECTED_POSITIONS} canonical "
                "positions, found "
                f"{len(canonical_verses)}"
            )

        source_positions = {}
        source_chapters = set()
        blank_positions = set()

        for book_position, (
            book_name,
            chapters,
        ) in enumerate(
            books.items(),
            start=1,
        ):
            if not isinstance(chapters, list):
                raise CommandError(
                    f"{book_name}: chapters must be a list."
                )

            if not chapters:
                raise CommandError(
                    f"{book_name}: no chapters found."
                )

            for chapter_number, verses in enumerate(
                chapters,
                start=1,
            ):
                if not isinstance(verses, list):
                    raise CommandError(
                        f"{book_name} {chapter_number}: "
                        "verses must be a list."
                    )

                source_chapters.add(
                    (book_position, chapter_number)
                )

                for verse_number, raw_text in enumerate(
                    verses,
                    start=1,
                ):
                    key = (
                        book_position,
                        chapter_number,
                        verse_number,
                    )

                    if key in source_positions:
                        raise CommandError(
                            "Duplicate source position: "
                            f"{key}"
                        )

                    text = normalize_text(raw_text)
                    source_positions[key] = text

                    if not text:
                        blank_positions.add(key)
                        continue

                    if "\ufffd" in text:
                        raise CommandError(
                            "Replacement character at "
                            f"{key}"
                        )

                    if re.search(r"<[^>]+>", text):
                        raise CommandError(
                            "Unexpected HTML marker at "
                            f"{key}"
                        )

        if len(source_chapters) != EXPECTED_CHAPTERS:
            raise CommandError(
                f"Expected {EXPECTED_CHAPTERS} chapters, "
                f"found {len(source_chapters)}"
            )

        if len(source_positions) != EXPECTED_POSITIONS:
            raise CommandError(
                f"Expected {EXPECTED_POSITIONS} source "
                f"positions, found {len(source_positions)}"
            )

        missing = (
            set(canonical_verses) - set(source_positions)
        )
        extra = (
            set(source_positions) - set(canonical_verses)
        )

        if missing or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {sorted(missing)[:20]}; "
                f"extra: {sorted(extra)[:20]}"
            )

        if blank_positions != EXPECTED_BLANKS:
            unexpected_blanks = (
                blank_positions - EXPECTED_BLANKS
            )
            missing_blanks = (
                EXPECTED_BLANKS - blank_positions
            )

            raise CommandError(
                "Intentional-blank validation failed. "
                "Unexpected blanks: "
                f"{sorted(unexpected_blanks)}; "
                "expected blanks containing text: "
                f"{sorted(missing_blanks)}"
            )

        source_texts = {
            key: text
            for key, text in source_positions.items()
            if text
        }

        if len(source_texts) != EXPECTED_TEXTS:
            raise CommandError(
                f"Expected {EXPECTED_TEXTS} nonblank "
                f"texts, found {len(source_texts)}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation=EXPECTED_VERSION,
                    defaults={
                        "name": EXPECTED_NAME,
                        "language": "English",
                        "year": 2012,
                    },
                )
            )

            version.name = EXPECTED_NAME
            version.language = "English"
            version.year = 2012
            version.description = (
                f"{ATTRIBUTION} The complete Lexham "
                "English Bible may be given away but "
                "must not be sold on its own. Source "
                "metadata: Copyright 2010, 2012 Logos "
                "Research Systems, Inc."
            )
            version.pdf_filename = "LEB.pdf"
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
                for key, text in source_texts.items()
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
        self.stdout.write("Language: English")
        self.stdout.write("Year: 2012")
        self.stdout.write(
            f"Books: {len(books)}"
        )
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Canonical positions: "
            f"{len(source_positions)}"
        )
        self.stdout.write(
            f"Imported verse texts: "
            f"{len(verse_texts)}"
        )
        self.stdout.write(
            f"Intentional blank positions: "
            f"{len(blank_positions)}"
        )
        self.stdout.write("PDF: LEB.pdf")
        self.stdout.write(
            f"Attribution: {ATTRIBUTION}"
        )
