import json
import re
from collections import Counter
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


EXPECTED_VERSION = "f35"
EXPECTED_DESCRIPTION = "Family 35"
EXPECTED_LANGUAGE = "grc"
EXPECTED_LICENSE = (
    "Creative Commons: by-nc-sa"
)
EXPECTED_BOOKS = 27
EXPECTED_CHAPTERS = 260
EXPECTED_POSITIONS = 7957
EXPECTED_TEXTS = 7950

EXPECTED_BLANKS = {
    (42, 17, 36),  # Luke 17:36
    (44, 8, 37),   # Acts 8:37
    (44, 15, 34),  # Acts 15:34
    (44, 24, 7),   # Acts 24:7
    (45, 16, 25),  # Romans 16:25
    (45, 16, 26),  # Romans 16:26
    (45, 16, 27),  # Romans 16:27
}

ATTRIBUTION = (
    "Family 35 Greek New Testament text by "
    "Wilbur N. Pickering, representing the Family "
    "35 group of Byzantine Greek manuscripts. "
    "Distributed under the Creative Commons "
    "Attribution-NonCommercial-ShareAlike 4.0 "
    "International license (CC BY-NC-SA 4.0)."
)


def collect_strings(value):
    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        strings = []

        for item in value:
            strings.extend(collect_strings(item))

        return strings

    raise CommandError(
        "Unexpected source verse value type: "
        f"{type(value).__name__}"
    )


def normalize_text(value):
    strings = collect_strings(value)

    return re.sub(
        r"\s+",
        " ",
        " ".join(strings),
    ).strip()


class Command(BaseCommand):
    help = (
        "Import the Family 35 Greek New Testament "
        "from the validated F35 JSON source."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help="Path to f35.json",
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

        if data.get("versionName") is not None:
            raise CommandError(
                "Unexpected source version name: "
                f"{data.get('versionName')!r}"
            )

        metadata = data.get("meta")

        if not isinstance(metadata, dict):
            raise CommandError(
                "Source metadata is missing or invalid."
            )

        if (
            metadata.get("description")
            != EXPECTED_DESCRIPTION
        ):
            raise CommandError(
                "Unexpected source description: "
                f"{metadata.get('description')!r}"
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

        if metadata.get("source") != "sword":
            raise CommandError(
                "Unexpected source type: "
                f"{metadata.get('source')!r}"
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
            for verse in Verse.objects.filter(
                chapter__book__position__gte=40,
                chapter__book__position__lte=66,
            ).select_related(
                "chapter__book",
            )
        }

        if len(canonical_verses) != EXPECTED_POSITIONS:
            raise CommandError(
                f"Expected {EXPECTED_POSITIONS} canonical "
                "New Testament positions, found "
                f"{len(canonical_verses)}"
            )

        source_positions = {}
        source_chapters = set()
        blank_positions = set()
        leaf_counts = Counter()

        for book_position, (
            book_name,
            chapters,
        ) in enumerate(
            books.items(),
            start=40,
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

                for verse_number, raw_value in enumerate(
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

                    strings = collect_strings(raw_value)
                    leaf_counts[len(strings)] += 1
                    text = normalize_text(raw_value)

                    source_positions[key] = text

                    if not text:
                        blank_positions.add(key)
                        continue

                    if len(strings) != 1:
                        raise CommandError(
                            "Expected one text leaf at "
                            f"{key}, found {len(strings)}"
                        )

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

                    if not re.search(
                        r"[\u0370-\u03ff\u1f00-\u1fff]",
                        text,
                    ):
                        raise CommandError(
                            "No Greek characters at "
                            f"{key}: {text!r}"
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
            expected_blanks_with_text = (
                EXPECTED_BLANKS - blank_positions
            )

            raise CommandError(
                "Intentional-blank validation failed. "
                "Unexpected blanks: "
                f"{sorted(unexpected_blanks)}; "
                "expected blanks containing text: "
                f"{sorted(expected_blanks_with_text)}"
            )

        if leaf_counts != {
            0: len(EXPECTED_BLANKS),
            1: EXPECTED_TEXTS,
        }:
            raise CommandError(
                "Unexpected nested-text structure: "
                f"{dict(leaf_counts)}"
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
                    abbreviation="F35",
                    defaults={
                        "name": (
                            "Family 35 Greek New Testament"
                        ),
                        "language": "Ancient Greek",
                        "year": 2014,
                    },
                )
            )

            version.name = (
                "Family 35 Greek New Testament"
            )
            version.language = "Ancient Greek"
            version.year = 2014
            version.description = ATTRIBUTION
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
        self.stdout.write("Language: Ancient Greek")
        self.stdout.write("Year: 2014")
        self.stdout.write("Books: 27")
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Canonical NT positions: "
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
        self.stdout.write(
            "License: CC BY-NC-SA 4.0"
        )
        self.stdout.write(
            "PDF: not configured; supplied PDF is "
            "an English translation/commentary"
        )
