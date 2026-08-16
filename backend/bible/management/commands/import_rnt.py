import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Book, Verse, VerseText


OSIS_TO_POSITION = {
    "Matt": 40,
    "Mark": 41,
    "Luke": 42,
    "John": 43,
    "Acts": 44,
    "Rom": 45,
    "1Cor": 46,
    "2Cor": 47,
    "Gal": 48,
    "Eph": 49,
    "Phil": 50,
    "Col": 51,
    "1Thess": 52,
    "2Thess": 53,
    "1Tim": 54,
    "2Tim": 55,
    "Titus": 56,
    "Phlm": 57,
    "Heb": 58,
    "Jas": 59,
    "1Pet": 60,
    "2Pet": 61,
    "1John": 62,
    "2John": 63,
    "3John": 64,
    "Jude": 65,
    "Rev": 66,
}

VERSE_ID_PATTERN = re.compile(
    r"([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)"
)

EXPECTED_VERSE_COUNT = 7957
EXPECTED_BOOK_COUNT = 27
EXPECTED_CHAPTER_COUNT = 260



def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def clean_text(value):
    """Extract RNT text and reconstruct its source formatting."""
    if not hasattr(value, "itertext"):
        raise CommandError(
            "clean_text requires an XML verse element"
        )

    def local_name(tag):
        return tag.rsplit("}", 1)[-1]

    def normalize(parts):
        return " ".join("".join(parts).split())

    notes = [
        child
        for child in value
        if local_name(child.tag) == "note"
    ]

    if not notes:
        text = normalize(value.itertext())
        return text.replace("\\'97", "—")

    outside_parts = []

    if value.text:
        outside_parts.append(value.text)

    for child in value:
        if local_name(child.tag) != "note":
            outside_parts.extend(child.itertext())

        if child.tail:
            outside_parts.append(child.tail)

    # A note-only verse contains the complete verse text.
    # Otherwise notes represent parenthetical inline material.
    wrap_notes = bool(normalize(outside_parts))
    parts = []

    if value.text:
        parts.append(value.text)

    for child in value:
        child_text = normalize(child.itertext())

        if local_name(child.tag) == "note":
            if wrap_notes:
                parts.append(f" ({child_text}) ")
            else:
                parts.append(child_text)
        else:
            parts.extend(child.itertext())

        if child.tail:
            parts.append(child.tail)

    text = normalize(parts)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.replace("\\'97", "—")


def parse_osis(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise CommandError(f"Invalid XML: {error}") from error

    records = {}
    source_books = set()
    source_chapters = set()

    for element in root.iter():
        if local_name(element.tag) != "verse":
            continue

        verse_id = element.get("osisID") or element.get("sID")
        if not verse_id:
            raise CommandError("A verse element has no osisID or sID")

        match = VERSE_ID_PATTERN.fullmatch(verse_id)
        if not match:
            raise CommandError(f"Invalid verse ID: {verse_id}")

        osis_book, chapter_text, verse_text = match.groups()
        position = OSIS_TO_POSITION.get(osis_book)
        if position is None:
            raise CommandError(f"Unknown OSIS book: {osis_book}")

        key = (
            position,
            int(chapter_text),
            int(verse_text),
        )

        if key in records:
            raise CommandError(f"Duplicate verse ID: {verse_id}")

        text = clean_text(element)
        if not text:
            raise CommandError(f"Empty verse text: {verse_id}")

        records[key] = text
        source_books.add(position)
        source_chapters.add((position, key[1]))

    if len(source_books) != EXPECTED_BOOK_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_BOOK_COUNT} books, "
            f"parsed {len(source_books)}"
        )

    if len(source_chapters) != EXPECTED_CHAPTER_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_CHAPTER_COUNT} chapters, "
            f"parsed {len(source_chapters)}"
        )

    if len(records) != EXPECTED_VERSE_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_VERSE_COUNT} verses, "
            f"parsed {len(records)}"
        )

    return records, source_books, source_chapters


class Command(BaseCommand):
    help = (
        "Import the public-domain 1923 Riverside New "
        "Testament from an OSIS XML file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            help="Path to the Riverside OSIS XML file",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.is_file():
            raise CommandError(f"File not found: {file_path}")

        records, source_books, source_chapters = parse_osis(file_path)

        canonical_rows = Verse.objects.filter(
            chapter__book__position__gte=40,
        ).values_list(
            "chapter__book__position",
            "chapter__number",
            "number",
            "id",
        )

        canonical_map = {
            (position, chapter, verse): verse_id
            for position, chapter, verse, verse_id in canonical_rows
        }
        canonical_positions = set(canonical_map)
        source_positions = set(records)

        unmatched = sorted(source_positions - canonical_positions)
        if unmatched:
            preview = ", ".join(
                f"{position}:{chapter}:{verse}"
                for position, chapter, verse in unmatched[:20]
            )
            raise CommandError(
                f"Source positions without canonical rows: "
                f"{len(unmatched)} (first: {preview})"
            )

        missing = sorted(
            canonical_positions - source_positions
        )
        if missing:
            raise CommandError(
                "Canonical positions without RNT text: "
                f"{missing[:20]}"
            )

        with transaction.atomic():
            version, version_created = (
                BibleVersion.objects.update_or_create(
                    abbreviation="RNT",
                    defaults={
                        "name": "Riverside New Testament",
                        "language": "English",
                        "year": 1923,
                        "pdf_filename": "",
                    },
                )
            )

            # Make repeated imports exactly match the current XML source.
            VerseText.objects.filter(bible_version=version).delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse_id=canonical_map[position],
                        text=text,
                    )
                    for position, text in records.items()
                ],
                batch_size=2000,
            )

        action = "Created" if version_created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})\n"
                f"Source OSIS verses: {len(records)}\n"
                f"Books: {len(source_books)}\n"
                f"Chapters: {len(source_chapters)}\n"
                f"Verse texts: {len(records)}\n"
                "Canonical NT positions without RNT text: "
                f"{len(missing)}\n"
                "RNT positions without a canonical row: 0"
            )
        )
