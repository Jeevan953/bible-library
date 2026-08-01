import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


BOOK_POSITIONS = {
    "GEN": 1, "EXO": 2, "LEV": 3, "NUM": 4, "DEU": 5,
    "JOS": 6, "JDG": 7, "RUT": 8,
    "1SA": 9, "2SA": 10, "1KI": 11, "2KI": 12,
    "1CH": 13, "2CH": 14, "EZR": 15, "NEH": 16,
    "JOB": 18, "PSA": 19, "PRO": 20, "ECC": 21,
    "SNG": 22, "ISA": 23, "JER": 24, "LAM": 25,
    "EZK": 26, "HOS": 28, "JOL": 29, "AMO": 30,
    "OBA": 31, "JON": 32, "MIC": 33, "NAM": 34,
    "HAB": 35, "ZEP": 36, "HAG": 37, "ZEC": 38,
    "MAL": 39,
}

ID_PATTERN = re.compile(r"^\\id\s+([A-Z0-9]+)\b")
CHAPTER_PATTERN = re.compile(r"^\\c\s+(\d+)\b")
VERSE_PATTERN = re.compile(
    r"^\\v\s+(\d+)[a-z]?\s*(.*)$",
    re.IGNORECASE,
)

NOTE_PATTERN = re.compile(
    r"\\(?:f|x)\s+.*?\\(?:f|x)\*",
    re.DOTALL,
)


def clean_usfm(text):
    text = NOTE_PATTERN.sub(" ", text)

    # Retain words inside character formatting such as:
    # \add word\add* and \sc word\sc*
    text = re.sub(
        r"\\\+?[A-Za-z0-9]+\*",
        " ",
        text,
    )
    text = re.sub(
        r"\\\+?[A-Za-z0-9]+\s*",
        " ",
        text,
    )

    text = text.replace("~", " ")

    return re.sub(r"\s+", " ", text).strip()


def parse_usfm(path):
    chapters = defaultdict(dict)

    current_chapter = None
    current_verse = None
    buffer = []

    def save_verse():
        nonlocal buffer

        if current_chapter is None or current_verse is None:
            buffer = []
            return

        text = clean_usfm(" ".join(buffer))

        if text:
            chapters[current_chapter][current_verse] = text

        buffer = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()

        chapter_match = CHAPTER_PATTERN.match(line)

        if chapter_match:
            save_verse()
            current_chapter = int(chapter_match.group(1))
            current_verse = None
            chapters[current_chapter]
            continue

        verse_match = VERSE_PATTERN.match(line)

        if verse_match:
            save_verse()
            current_verse = int(verse_match.group(1))
            buffer = [verse_match.group(2)]
            continue

        if current_verse is not None and line:
            buffer.append(line)

    save_verse()

    return chapters


class Command(BaseCommand):
    help = "Import safe, exactly aligned Brenton chapters."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        paths = {}

        for path in folder.glob("*.usfm"):
            for line in path.read_text(
                encoding="utf-8-sig"
            ).splitlines():
                match = ID_PATTERN.match(line.strip())

                if match:
                    code = match.group(1).upper()

                    if code in BOOK_POSITIONS:
                        paths[code] = path

                    break

        missing_files = sorted(
            set(BOOK_POSITIONS) - set(paths)
        )

        if missing_files:
            raise CommandError(
                "Missing source files: "
                + ", ".join(missing_files)
            )

        import_rows = []
        exact_chapters = 0
        mismatched_chapters = 0
        extra_chapters = 0
        missing_chapters = 0

        for code, position in BOOK_POSITIONS.items():
            source = parse_usfm(paths[code])

            canonical = defaultdict(dict)

            verses = (
                Verse.objects.filter(
                    chapter__book__position=position
                )
                .select_related("chapter")
                .order_by("chapter__number", "number")
            )

            for verse in verses:
                canonical[verse.chapter.number][
                    verse.number
                ] = verse

            extra_chapters += len(
                set(source) - set(canonical)
            )
            missing_chapters += len(
                set(canonical) - set(source)
            )

            for chapter_number in sorted(
                set(source) & set(canonical)
            ):
                source_numbers = set(
                    source[chapter_number]
                )
                canonical_numbers = set(
                    canonical[chapter_number]
                )

                if source_numbers != canonical_numbers:
                    mismatched_chapters += 1
                    continue

                exact_chapters += 1

                for number in sorted(source_numbers):
                    import_rows.append(
                        (
                            canonical[chapter_number][number],
                            source[chapter_number][number],
                        )
                    )

        pdf_path = folder.parent / "Brenton.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="BRENTON",
                    defaults={
                        "name": "Brenton English Septuagint",
                        "language": "English",
                    },
                )
            )

            version.name = "Brenton English Septuagint"
            version.language = "English"
            version.pdf_filename = "Brenton.pdf"
            version.description = (
                "Brenton English Septuagint. "
                "Currently includes only chapters whose "
                "verse numbering exactly matches the canonical "
                "database. Septuagint-specific chapters and "
                "versification require separate mapping."
            )

            version.save(
                update_fields=[
                    "name",
                    "language",
                    "pdf_filename",
                    "description",
                ]
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse=verse,
                        text=text,
                    )
                    for verse, text in import_rows
                ],
                batch_size=2000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: "
                f"{version.name} ({version.abbreviation})"
            )
        )
        self.stdout.write(
            f"Compatible books: {len(paths)}"
        )
        self.stdout.write(
            f"Exact chapters imported: {exact_chapters}"
        )
        self.stdout.write(
            f"Verse texts imported: {len(import_rows)}"
        )
        self.stdout.write(
            f"Mismatched chapters skipped: "
            f"{mismatched_chapters}"
        )
        self.stdout.write(
            f"Extra source chapters skipped: "
            f"{extra_chapters}"
        )
        self.stdout.write(
            f"Missing source chapters: {missing_chapters}"
        )
