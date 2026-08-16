import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


OSIS_NAMESPACE = {
    "osis": "http://www.bibletechnologies.net/2003/OSIS/namespace",
}

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

POSITION_TO_NAME = {
    40: "Matthew",
    41: "Mark",
    42: "Luke",
    43: "John",
    44: "Acts",
    45: "Romans",
    46: "1 Corinthians",
    47: "2 Corinthians",
    48: "Galatians",
    49: "Ephesians",
    50: "Philippians",
    51: "Colossians",
    52: "1 Thessalonians",
    53: "2 Thessalonians",
    54: "1 Timothy",
    55: "2 Timothy",
    56: "Titus",
    57: "Philemon",
    58: "Hebrews",
    59: "James",
    60: "1 Peter",
    61: "2 Peter",
    62: "1 John",
    63: "2 John",
    64: "3 John",
    65: "Jude",
    66: "Revelation",
}

VERSE_ID_PATTERN = re.compile(r"([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)")


def clean_text(parts):
    return " ".join("".join(parts).split())


def parse_osis(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise CommandError(f"Invalid OSIS XML: {error}") from error

    parsed = {}
    duplicate_ids = []
    invalid_ids = []
    unknown_books = []
    empty_ids = []

    for element in root.findall(".//osis:verse", OSIS_NAMESPACE):
        verse_id = element.get("osisID", "")
        match = VERSE_ID_PATTERN.fullmatch(verse_id)

        if not match:
            invalid_ids.append(verse_id or "(missing osisID)")
            continue

        book_code, chapter_number, verse_number = match.groups()
        book_position = OSIS_TO_POSITION.get(book_code)

        if book_position is None:
            unknown_books.append(book_code)
            continue

        text = clean_text(element.itertext())
        if not text:
            empty_ids.append(verse_id)
            continue

        key = (book_position, int(chapter_number), int(verse_number))
        if key in parsed:
            duplicate_ids.append(verse_id)
            continue

        parsed[key] = text

    problems = []
    if duplicate_ids:
        problems.append(f"duplicate verse IDs: {duplicate_ids[:10]}")
    if invalid_ids:
        problems.append(f"invalid verse IDs: {invalid_ids[:10]}")
    if unknown_books:
        problems.append(f"unknown book codes: {sorted(set(unknown_books))}")
    if empty_ids:
        problems.append(f"empty verses: {empty_ids[:10]}")

    if problems:
        raise CommandError("; ".join(problems))

    return parsed


def format_position(position):
    book_position, chapter_number, verse_number = position
    book_name = POSITION_TO_NAME.get(book_position, str(book_position))
    return f"{book_name} {chapter_number}:{verse_number}"


class Command(BaseCommand):
    help = "Import the public-domain Emphatic Diaglott interlinear English NT from OSIS XML."

    def add_arguments(self, parser):
        parser.add_argument("xml_path", type=Path)

    def handle(self, *args, **options):
        path = options["xml_path"]
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        parsed = parse_osis(path)
        original_verse_count = len(parsed)

        # The source uses the 15-verse numbering for 3 John. The canonical
        # database uses 14 verses, so retain both source verses under 1:14.
        verse_15 = parsed.pop((64, 1, 15), None)
        merged_3_john = False
        if verse_15:
            verse_14_key = (64, 1, 14)
            verse_14 = parsed.get(verse_14_key)
            if not verse_14:
                raise CommandError(
                    "Cannot merge 3 John 1:15 because source verse 1:14 is missing."
                )
            parsed[verse_14_key] = clean_text([verse_14, " ", verse_15])
            merged_3_john = True

        canonical_rows = Verse.objects.filter(
            chapter__book__position__gte=40,
            chapter__book__position__lte=66,
        ).select_related("chapter__book")

        canonical = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in canonical_rows
        }

        unmatched = sorted(set(parsed) - set(canonical))
        matched_positions = sorted(set(parsed) & set(canonical))
        missing = sorted(set(canonical) - set(parsed))

        if unmatched:
            preview = ", ".join(format_position(item) for item in unmatched[:10])
            raise CommandError(
                f"{len(unmatched)} XML positions lack a canonical Verse row "
                f"(first: {preview})"
            )

        with transaction.atomic():
            version, created = BibleVersion.objects.update_or_create(
                abbreviation="ED",
                defaults={
                    "name": "The Emphatic Diaglott (Interlinear English)",
                    "language": "English",
                    "year": 1865,
                    "pdf_filename": "",
                },
            )

            VerseText.objects.filter(bible_version=version).delete()
            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse=canonical[position],
                        text=parsed[position],
                    )
                    for position in matched_positions
                ],
                batch_size=1000,
            )

        status = "Created" if created else "Updated"
        books = len({position for position, _, _ in parsed})
        chapters = len({(position, chapter) for position, chapter, _ in parsed})

        self.stdout.write(
            self.style.SUCCESS(
                f"{status}: {version.name} ({version.abbreviation})"
            )
        )
        self.stdout.write(f"Source OSIS verses: {original_verse_count}")
        self.stdout.write(f"Books: {books}")
        self.stdout.write(f"Chapters: {chapters}")
        self.stdout.write(f"Verse texts: {len(matched_positions)}")
        self.stdout.write(
            "3 John 1:15 merged into canonical 1:14: "
            f"{'yes' if merged_3_john else 'not present'}"
        )
        self.stdout.write(
            f"Canonical NT positions without Diaglott text: {len(missing)}"
        )
        if missing:
            preview = ", ".join(format_position(item) for item in missing[:10])
            self.stdout.write(f"Missing positions: {preview}")
