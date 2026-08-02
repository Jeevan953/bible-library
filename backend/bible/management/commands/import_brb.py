import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Book,
    Chapter,
    Verse,
    VerseText,
)


CHAPTER_HEADER_PATTERN = re.compile(
    r"^(.+?)\s+(\d+)$"
)

EXPECTED_PREAMBLE = [
    (
        "The Holy Bible, Berean Reader’s Bible, "
        "Copyright © 2020 by Bible Hub. "
        "All Rights Reserved Worldwide."
    ),
    (
        "Free Licensing for use in Websites, Apps, "
        "Software, and Audio:  "
        "http://berean.bible/licensing.htm"
    ),
]

EXPECTED_EMPTY_KEYS = {
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


class Command(BaseCommand):
    help = "Import Berean Reader's Bible."

    def add_arguments(self, parser):
        parser.add_argument("filename", type=str)

    def handle(self, *args, **options):
        path = Path(options["filename"])

        if not path.is_file():
            raise CommandError(
                f"File not found: {path}"
            )

        pdf_path = path.parent / "brb.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        try:
            content = path.read_text(
                encoding="cp1252"
            )
        except UnicodeDecodeError as error:
            raise CommandError(
                f"Unable to decode source as cp1252: {error}"
            ) from error

        books = list(
            Book.objects.order_by("position")
        )

        book_aliases = {
            book.name.casefold(): book.position
            for book in books
        }

        book_aliases.update({
            "psalm": 19,
            "psalms": 19,
            "song of solomon": 22,
            "song of songs": 22,
        })

        valid_chapters = set(
            Chapter.objects.values_list(
                "book__position",
                "number",
            )
        )

        canonical_by_chapter = defaultdict(list)
        canonical_keys = set()

        for verse in (
            Verse.objects.select_related(
                "chapter__book"
            )
            .order_by(
                "chapter__book__position",
                "chapter__number",
                "number",
            )
        ):
            key = (
                verse.chapter.book.position,
                verse.chapter.number,
            )

            canonical_by_chapter[key].append(
                verse
            )

            canonical_keys.add(
                (
                    key[0],
                    key[1],
                    verse.number,
                )
            )

        source_chapters = defaultdict(list)
        detected_headers = []
        detected_keys = set()
        duplicate_headers = []
        preamble = []
        current_key = None
        blank_lines = 0

        for line_number, raw_line in enumerate(
            content.splitlines(),
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                blank_lines += 1
                continue

            match = CHAPTER_HEADER_PATTERN.fullmatch(
                line
            )

            if match:
                source_book = match.group(1).strip()
                chapter_number = int(
                    match.group(2)
                )

                book_position = book_aliases.get(
                    source_book.casefold()
                )

                candidate = (
                    book_position,
                    chapter_number,
                )

                if (
                    book_position is not None
                    and candidate in valid_chapters
                ):
                    if candidate in detected_keys:
                        duplicate_headers.append(
                            (line_number, line)
                        )

                    detected_keys.add(candidate)
                    detected_headers.append(
                        (
                            line_number,
                            candidate,
                            line,
                        )
                    )
                    current_key = candidate
                    continue

            if current_key is None:
                preamble.append(line)
            else:
                source_chapters[
                    current_key
                ].append(
                    (line_number, line)
                )

        errors = []

        if preamble != EXPECTED_PREAMBLE:
            errors.append(
                "Source preamble differs from expected. "
                f"Found: {preamble!r}"
            )

        if len(books) != 66:
            errors.append(
                f"Expected 66 books, found {len(books)}"
            )

        if len(valid_chapters) != 1189:
            errors.append(
                "Expected 1189 canonical chapters, "
                f"found {len(valid_chapters)}"
            )

        if len(detected_headers) != 1189:
            errors.append(
                "Expected 1189 chapter headers, "
                f"found {len(detected_headers)}"
            )

        missing_headers = (
            valid_chapters - detected_keys
        )

        if missing_headers:
            errors.append(
                "Missing chapter headers: "
                f"{sorted(missing_headers)}"
            )

        if duplicate_headers:
            errors.append(
                "Duplicate chapter headers: "
                f"{duplicate_headers}"
            )

        source_rows = {}
        chapter_headings = {}
        count_mismatches = []

        for key in sorted(valid_chapters):
            chapter_rows = source_chapters.get(
                key,
                [],
            )

            if not chapter_rows:
                count_mismatches.append(
                    (
                        key,
                        "no chapter content",
                    )
                )
                continue

            heading_line, heading = chapter_rows[0]

            chapter_headings[key] = {
                "line": heading_line,
                "text": heading,
            }

            source_verse_lines = chapter_rows[1:]

            expected_verses = [
                verse
                for verse in canonical_by_chapter[key]
                if (
                    key[0],
                    key[1],
                    verse.number,
                ) not in EXPECTED_EMPTY_KEYS
            ]

            if (
                len(source_verse_lines)
                != len(expected_verses)
            ):
                count_mismatches.append(
                    (
                        key,
                        len(source_verse_lines),
                        len(expected_verses),
                    )
                )
                continue

            for (
                (line_number, text),
                verse,
            ) in zip(
                source_verse_lines,
                expected_verses,
            ):
                source_rows[
                    (
                        key[0],
                        key[1],
                        verse.number,
                    )
                ] = {
                    "verse": verse,
                    "text": text,
                    "line": line_number,
                }

        if count_mismatches:
            errors.append(
                "Chapter verse-line counts differ from "
                "the expected canonical positions: "
                f"{count_mismatches[:30]}"
            )

        if len(chapter_headings) != 1189:
            errors.append(
                "Expected 1189 section headings, found "
                f"{len(chapter_headings)}"
            )

        if len(source_rows) != 31086:
            errors.append(
                "Expected 31086 verse texts, found "
                f"{len(source_rows)}"
            )

        imported_keys = set(source_rows)
        empty_keys = canonical_keys - imported_keys

        if empty_keys != EXPECTED_EMPTY_KEYS:
            errors.append(
                "Empty positions differ from expected. "
                f"Unexpected: "
                f"{sorted(empty_keys - EXPECTED_EMPTY_KEYS)}; "
                f"missing: "
                f"{sorted(EXPECTED_EMPTY_KEYS - empty_keys)}"
            )

        if "\ufffd" in content:
            errors.append(
                "Replacement characters found in source"
            )

        if errors:
            raise CommandError(
                "BRB validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="BRB",
                    defaults={
                        "name": (
                            "Berean Reader's Bible"
                        ),
                        "language": "English",
                        "year": 2020,
                        "description": (
                            "Berean Reader's Bible, "
                            "copyright 2020 by Bible Hub. "
                            "Imported under the licensing "
                            "terms published at "
                            "http://berean.bible/"
                            "licensing.htm."
                        ),
                        "pdf_filename": "brb.pdf",
                    },
                )
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            verse_texts = [
                VerseText(
                    bible_version=version,
                    verse=row["verse"],
                    text=row["text"],
                )
                for row in source_rows.values()
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
        self.stdout.write("Encoding: cp1252")
        self.stdout.write("Books: 66")
        self.stdout.write("Chapters: 1189")
        self.stdout.write(
            f"Section headings ignored: "
            f"{len(chapter_headings)}"
        )
        self.stdout.write(
            f"Verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Empty verse positions: "
            f"{len(empty_keys)}"
        )
        self.stdout.write(
            f"Ignored preamble lines: "
            f"{len(preamble)}"
        )
        self.stdout.write(
            f"Ignored blank lines: {blank_lines}"
        )
