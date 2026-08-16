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


EXPECTED_MISSING = {
    (40, 18, 11),
    (40, 23, 14),
    (41, 7, 16),
    (41, 9, 44),
    (41, 9, 46),
    (41, 15, 28),
    (42, 17, 36),
    (42, 23, 17),
    (43, 5, 4),
    (44, 8, 37),
    (44, 15, 34),
    (44, 24, 7),
}

LEGACY_TOKEN = "\\fs15"
LEGACY_PATTERN = re.compile(
    r"\\[A-Za-z]+-?\d*"
)


def parse_osis(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise CommandError(f"Invalid XML: {error}") from error

    records = {}
    source_positions = set()
    source_books = set()
    source_chapters = set()
    seen_ids = set()

    invalid_ids = []
    unknown_books = []
    duplicate_ids = []
    duplicate_positions = []
    empty_positions = []
    unexpected_tokens = []

    legacy_count = 0
    matthew_remapped = False

    for element in root.findall(
        ".//osis:verse",
        OSIS_NAMESPACE,
    ):
        verse_id = element.get("osisID")

        if not verse_id:
            continue

        if verse_id in seen_ids:
            duplicate_ids.append(verse_id)
            continue

        seen_ids.add(verse_id)

        match = VERSE_ID_PATTERN.fullmatch(verse_id)

        if not match:
            invalid_ids.append(verse_id)
            continue

        osis_book, chapter_text, verse_text = (
            match.groups()
        )
        position = OSIS_TO_POSITION.get(osis_book)

        if position is None:
            unknown_books.append(osis_book)
            continue

        chapter = int(chapter_text)
        verse = int(verse_text)
        source_key = (position, chapter, verse)

        source_positions.add(source_key)
        source_books.add(position)
        source_chapters.add((position, chapter))

        value = clean_text(element.itertext())
        tokens = LEGACY_PATTERN.findall(value)

        legacy_count += tokens.count(LEGACY_TOKEN)

        unexpected_tokens.extend(
            token
            for token in tokens
            if token != LEGACY_TOKEN
        )

        value = " ".join(
            value.replace(LEGACY_TOKEN, "").split()
        )

        if not value:
            empty_positions.append(source_key)
            continue

        target_key = source_key

        # This XML places Rotherham's Matthew 23:13
        # text under OSIS ID Matt.23.14. Canonical 23:14
        # remains intentionally absent.
        if source_key == (40, 23, 14):
            if (
                "locking up the kingdom of the heavens"
                not in value
            ):
                raise CommandError(
                    "Matt.23.14 does not contain the "
                    "expected Rotherham Matthew 23:13 text"
                )

            target_key = (40, 23, 13)
            matthew_remapped = True

        if target_key in records:
            duplicate_positions.append(target_key)
            continue

        records[target_key] = value

    problems = []

    if len(seen_ids) != 31090:
        problems.append(
            f"Expected 31090 source verses, "
            f"found {len(seen_ids)}"
        )

    if len(source_books) != 66:
        problems.append(
            f"Expected 66 books, found {len(source_books)}"
        )

    if len(source_chapters) != 1189:
        problems.append(
            "Expected 1189 chapters, "
            f"found {len(source_chapters)}"
        )

    if legacy_count != 30:
        problems.append(
            "Expected 30 legacy font-size codes, "
            f"found {legacy_count}"
        )

    if not matthew_remapped:
        problems.append(
            "Matt.23.14 was not remapped to "
            "canonical Matthew 23:13"
        )

    if invalid_ids:
        problems.append(
            "Invalid IDs: " + ", ".join(invalid_ids[:20])
        )

    if unknown_books:
        problems.append(
            "Unknown books: "
            + ", ".join(sorted(set(unknown_books)))
        )

    if duplicate_ids:
        problems.append(
            "Duplicate IDs: "
            + ", ".join(duplicate_ids[:20])
        )

    if duplicate_positions:
        problems.append(
            "Duplicate positions: "
            + ", ".join(
                format_position(position)
                for position in duplicate_positions[:20]
            )
        )

    if empty_positions:
        problems.append(
            "Empty positions: "
            + ", ".join(
                format_position(position)
                for position in empty_positions[:20]
            )
        )

    if unexpected_tokens:
        problems.append(
            "Unexpected legacy tokens: "
            + ", ".join(
                sorted(set(unexpected_tokens))
            )
        )

    remaining_tokens = sorted({
        token
        for value in records.values()
        for token in LEGACY_PATTERN.findall(value)
    })

    if remaining_tokens:
        problems.append(
            "Legacy tokens remain after cleaning: "
            + ", ".join(remaining_tokens)
        )

    if problems:
        raise CommandError("\n".join(problems))

    return (
        records,
        source_books,
        source_chapters,
        len(seen_ids),
        legacy_count,
        matthew_remapped,
    )


class Command(BaseCommand):
    help = (
        "Import the public-domain 1902 Rotherham "
        "Emphasized Bible from an OSIS XML file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "xml_path",
            type=Path,
            help="Path to the Rotherham OSIS XML file",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        xml_path = options["xml_path"]

        if not xml_path.is_file():
            raise CommandError(
                f"File not found: {xml_path}"
            )

        (
            records,
            source_books,
            source_chapters,
            source_count,
            legacy_count,
            matthew_remapped,
        ) = parse_osis(xml_path)

        canonical = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.select_related(
                "chapter__book"
            )
        }

        canonical_positions = set(canonical)
        imported_positions = set(records)

        unmatched = sorted(
            imported_positions - canonical_positions
        )
        missing = sorted(
            canonical_positions - imported_positions
        )

        if unmatched:
            raise CommandError(
                "Rotherham positions without a canonical row: "
                + ", ".join(
                    format_position(position)
                    for position in unmatched[:20]
                )
            )

        if set(missing) != EXPECTED_MISSING:
            raise CommandError(
                "Unexpected canonical positions without "
                "Rotherham text: "
                + ", ".join(
                    format_position(position)
                    for position in missing[:30]
                )
            )

        version, created = BibleVersion.objects.update_or_create(
            abbreviation="ROTH",
            defaults={
                "name": "Rotherham Emphasized Bible",
                "language": "English",
                "year": 1902,
                "pdf_filename": "",
            },
        )

        VerseText.objects.filter(
            bible_version=version
        ).delete()

        VerseText.objects.bulk_create(
            [
                VerseText(
                    bible_version=version,
                    verse=canonical[position],
                    text=verse_text,
                )
                for position, verse_text
                in sorted(records.items())
            ],
            batch_size=1000,
        )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})"
            )
        )
        self.stdout.write(
            f"Source OSIS verses: {source_count}"
        )
        self.stdout.write(
            f"Books: {len(source_books)}"
        )
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Verse texts: {len(records)}"
        )
        self.stdout.write(
            "Matthew 23:14 remapped to canonical "
            "23:13: "
            + ("yes" if matthew_remapped else "no")
        )
        self.stdout.write(
            f"Legacy font-size codes removed: "
            f"{legacy_count}"
        )
        self.stdout.write(
            "Canonical positions without Rotherham text: "
            f"{len(missing)}"
        )
        self.stdout.write(
            "Missing positions: "
            + ", ".join(
                format_position(position)
                for position in missing
            )
        )
        self.stdout.write(
            "Rotherham positions without a canonical row: 0"
        )
