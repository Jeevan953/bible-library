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
    "Gen": 1,
    "Exod": 2,
    "Lev": 3,
    "Num": 4,
    "Deut": 5,
    "Josh": 6,
    "Judg": 7,
    "Ruth": 8,
    "1Sam": 9,
    "2Sam": 10,
    "1Kgs": 11,
    "2Kgs": 12,
    "1Chr": 13,
    "2Chr": 14,
    "Ezra": 15,
    "Neh": 16,
    "Esth": 17,
    "Job": 18,
    "Ps": 19,
    "Prov": 20,
    "Eccl": 21,
    "Song": 22,
    "Isa": 23,
    "Jer": 24,
    "Lam": 25,
    "Ezek": 26,
    "Dan": 27,
    "Hos": 28,
    "Joel": 29,
    "Amos": 30,
    "Obad": 31,
    "Jonah": 32,
    "Mic": 33,
    "Nah": 34,
    "Hab": 35,
    "Zeph": 36,
    "Hag": 37,
    "Zech": 38,
    "Mal": 39,
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
    1: "Genesis",
    2: "Exodus",
    3: "Leviticus",
    4: "Numbers",
    5: "Deuteronomy",
    6: "Joshua",
    7: "Judges",
    8: "Ruth",
    9: "1 Samuel",
    10: "2 Samuel",
    11: "1 Kings",
    12: "2 Kings",
    13: "1 Chronicles",
    14: "2 Chronicles",
    15: "Ezra",
    16: "Nehemiah",
    17: "Esther",
    18: "Job",
    19: "Psalms",
    20: "Proverbs",
    21: "Ecclesiastes",
    22: "Song of Solomon",
    23: "Isaiah",
    24: "Jeremiah",
    25: "Lamentations",
    26: "Ezekiel",
    27: "Daniel",
    28: "Hosea",
    29: "Joel",
    30: "Amos",
    31: "Obadiah",
    32: "Jonah",
    33: "Micah",
    34: "Nahum",
    35: "Habakkuk",
    36: "Zephaniah",
    37: "Haggai",
    38: "Zechariah",
    39: "Malachi",
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


def format_position(position):
    book_position, chapter_number, verse_number = position
    book_name = POSITION_TO_NAME.get(book_position, str(book_position))
    return f"{book_name} {chapter_number}:{verse_number}"


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


class Command(BaseCommand):
    help = "Import the public-domain American King James Version from OSIS XML."

    def add_arguments(self, parser):
        parser.add_argument("xml_path", type=Path)

    def handle(self, *args, **options):
        path = options["xml_path"]
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        parsed = parse_osis(path)

        canonical_rows = Verse.objects.select_related("chapter__book")
        canonical = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in canonical_rows
        }

        parsed_positions = set(parsed)
        canonical_positions = set(canonical)
        unmatched = sorted(parsed_positions - canonical_positions)
        missing = sorted(canonical_positions - parsed_positions)

        if unmatched or missing:
            details = []
            if unmatched:
                preview = ", ".join(
                    format_position(position) for position in unmatched[:10]
                )
                details.append(
                    f"{len(unmatched)} XML positions lack a canonical row "
                    f"(first: {preview})"
                )
            if missing:
                preview = ", ".join(
                    format_position(position) for position in missing[:10]
                )
                details.append(
                    f"{len(missing)} canonical positions lack AKJV text "
                    f"(first: {preview})"
                )
            raise CommandError("; ".join(details))

        sorted_positions = sorted(parsed_positions)

        with transaction.atomic():
            version, created = BibleVersion.objects.update_or_create(
                abbreviation="AKJV",
                defaults={
                    "name": "American King James Version",
                    "language": "English",
                    "year": 1999,
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
                    for position in sorted_positions
                ],
                batch_size=1000,
            )

        status = "Created" if created else "Updated"
        books = len({position for position, _, _ in parsed_positions})
        chapters = len(
            {(position, chapter) for position, chapter, _ in parsed_positions}
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{status}: {version.name} ({version.abbreviation})"
            )
        )
        self.stdout.write(f"Books: {books}")
        self.stdout.write(f"Chapters: {chapters}")
        self.stdout.write(f"Verse texts: {len(sorted_positions)}")
        self.stdout.write("Canonical positions without AKJV text: 0")
        self.stdout.write("AKJV positions without a canonical row: 0")
