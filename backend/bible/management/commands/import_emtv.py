import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import (
    BibleVersion,
    Book,
    Chapter,
    Verse,
    VerseText,
)


BOOK_CODES = (
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
    "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
    "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
    "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
    "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT",
    "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL",
    "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT",
    "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN",
    "JUD", "REV",
)

NT_CODES = BOOK_CODES[39:]

FILE_PATTERN = re.compile(
    r"^\d+-(?P<code>[A-Z0-9]+)engemtv\.usfm$",
    re.IGNORECASE,
)

CHAPTER_PATTERN = re.compile(
    r"^\\c\s+(?P<number>\d+)\b"
)

VERSE_PATTERN = re.compile(
    r"^\\v\s+(?P<number>\d+)(?:[a-z])?\s*(?P<text>.*)$"
)

IGNORE_LINE_MARKERS = {
    "id", "ide", "h",
    "toc1", "toc2", "toc3",
    "mt", "mt1", "mt2", "mt3", "mt4",
    "mte", "mte1", "mte2",
    "s", "s1", "s2", "s3", "s4",
    "ms", "ms1", "ms2", "mr",
    "r", "d", "sp", "cl", "cp", "rem",
}


# These positions are absent from the EMTV source.
EXPECTED_MISSING = {
    ("LUK", 17, 36),
    ("ACT", 8, 37),
    ("ACT", 15, 34),
}


def clean_usfm(text):
    # Remove complete footnotes and cross-references.
    for marker in ("f", "fe", "x"):
        text = re.sub(
            rf"\\{marker}\b.*?\\{marker}\*",
            "",
            text,
            flags=re.DOTALL,
        )

    # Keep displayed words while removing Strong's attributes.
    text = re.sub(
        r"\\\+?w\s+([^|\\]*?)(?:\|[^\\]*?)?\\\+?w\*",
        r"\1",
        text,
    )

    # Remove any remaining USFM character markers but retain content.
    text = re.sub(
        r"\\[+A-Za-z0-9-]+\*?",
        "",
        text,
    )

    text = text.replace("\\*", "")
    text = text.replace("~", " ")

    return re.sub(r"\s+", " ", text).strip()


def parse_usfm(path, code):
    parsed = {}
    chapters_seen = set()

    current_chapter = None
    current_verse = None
    fragments = []

    def save_current_verse():
        nonlocal fragments

        if current_chapter is None or current_verse is None:
            fragments = []
            return

        text = clean_usfm(" ".join(fragments))

        if not text:
            raise CommandError(
                f"{path.name}: empty text at "
                f"{code} {current_chapter}:{current_verse}"
            )

        key = (code, current_chapter, current_verse)

        if key in parsed:
            raise CommandError(
                f"{path.name}: duplicate verse "
                f"{code} {current_chapter}:{current_verse}"
            )

        parsed[key] = text
        fragments = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        chapter_match = CHAPTER_PATTERN.match(line)

        if chapter_match:
            save_current_verse()

            current_chapter = int(
                chapter_match.group("number")
            )
            current_verse = None
            chapters_seen.add(current_chapter)
            continue

        verse_match = VERSE_PATTERN.match(line)

        if verse_match:
            save_current_verse()

            if current_chapter is None:
                raise CommandError(
                    f"{path.name}: verse found before chapter"
                )

            current_verse = int(
                verse_match.group("number")
            )
            fragments = [verse_match.group("text")]
            continue

        if current_verse is None:
            continue

        marker_match = re.match(
            r"^\\(?P<marker>[+A-Za-z0-9-]+)\b",
            line,
        )

        if marker_match:
            marker = marker_match.group("marker").lstrip("+")

            if marker in IGNORE_LINE_MARKERS:
                continue

        # Preserve poetry and multiline verse continuations.
        fragments.append(line)

    save_current_verse()

    return parsed, chapters_seen


def normalize_versification(source):
    normalized = {}

    for (code, chapter, number), text in source.items():
        # EMTV places the Romans doxology after chapter 14.
        if code == "ROM" and chapter == 14 and 24 <= number <= 26:
            target = ("ROM", 16, number + 1)
        else:
            target = (code, chapter, number)

        if target in normalized:
            raise CommandError(
                f"Multiple source verses map to {target}"
            )

        normalized[target] = text

    return normalized

class Command(BaseCommand):
    help = "Import the English Majority Text Version from USFM."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        pdf_path = folder.parent / "emtv.pdf"

        if not pdf_path.is_file():
            raise CommandError(f"PDF not found: {pdf_path}")

        canonical_codes = set(NT_CODES)
        paths = {}

        for path in folder.glob("*.usfm"):
            match = FILE_PATTERN.match(path.name)

            if not match:
                continue

            code = match.group("code").upper()

            # Ignore front matter and introduction files.
            if code not in canonical_codes:
                continue

            if code in paths:
                raise CommandError(
                    f"Duplicate USFM file for {code}"
                )

            paths[code] = path

        missing_files = [
            code for code in NT_CODES if code not in paths
        ]

        if missing_files:
            raise CommandError(
                "Missing canonical files: "
                + ", ".join(missing_files)
            )

        source = {}
        source_chapters = set()

        for code in NT_CODES:
            parsed, chapters = parse_usfm(paths[code], code)
            source.update(parsed)

            source_chapters.update(
                (code, chapter) for chapter in chapters
            )

        if len(source_chapters) != 260:
            raise CommandError(
                "Expected 260 chapters, found "
                f"{len(source_chapters)}"
            )

        if len(source) != 7954:
            raise CommandError(
                "Expected 7954 source texts, found "
                f"{len(source)}"
            )

        normalized = normalize_versification(source)

        if len(normalized) != 7954:
            raise CommandError(
                "Expected 7954 normalized texts, found "
                f"{len(normalized)}"
            )

        canonical_verses = {}
        canonical_chapters = set()

        for position, code in enumerate(NT_CODES, start=40):
            try:
                book = Book.objects.get(position=position)
            except Book.DoesNotExist as error:
                raise CommandError(
                    f"Canonical book position {position} not found"
                ) from error

            chapters = Chapter.objects.filter(
                book=book
            ).order_by("number")

            for chapter in chapters:
                canonical_chapters.add(
                    (code, chapter.number)
                )

                verses = Verse.objects.filter(
                    chapter=chapter
                ).order_by("number")

                for verse in verses:
                    key = (
                        code,
                        chapter.number,
                        verse.number,
                    )
                    canonical_verses[key] = verse

        chapter_errors = (
            source_chapters.symmetric_difference(
                canonical_chapters
            )
        )

        if chapter_errors:
            examples = sorted(chapter_errors)[:20]
            raise CommandError(
                f"Chapter validation failed: {examples}"
            )

        unexpected = (
            set(normalized) - set(canonical_verses)
        )
        actual_missing = (
            set(canonical_verses) - set(normalized)
        )
        unexpected_missing = (
            actual_missing - EXPECTED_MISSING
        )
        unexpectedly_present = (
            EXPECTED_MISSING - actual_missing
        )

        if (
            unexpected
            or unexpected_missing
            or unexpectedly_present
        ):
            messages = []

            if unexpected:
                messages.append(
                    f"Unexpected verses: {sorted(unexpected)[:20]}"
                )

            if unexpected_missing:
                messages.append(
                    "Unexpected missing verses: "
                    f"{sorted(unexpected_missing)[:20]}"
                )

            if unexpectedly_present:
                messages.append(
                    "Expected omissions contain text: "
                    f"{sorted(unexpectedly_present)[:20]}"
                )

            raise CommandError("\n".join(messages))

        with transaction.atomic():
            version, created = BibleVersion.objects.get_or_create(
                abbreviation="EMTV",
                defaults={
                    "name": "English Majority Text Version",
                    "language": "English",
                    "year": 1901,
                },
            )

            version.name = "English Majority Text Version"
            version.language = "English"
            version.year = 2014
            version.description = (
                "English Majority Text Version New Testament, "
                "translated by Dr. Paul W. Esposito. "
                "Copyright © 2014 Dr. Paul W. Esposito; "
                "CC BY-NC-ND 4.0."
            )
            version.pdf_filename = "emtv.pdf"
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
                for key, text in normalized.items()
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
        self.stdout.write("Books: 27")
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Source verses: {len(source)}"
        )
        self.stdout.write(
            f"Imported verses: {len(verse_texts)}"
        )
        self.stdout.write(
            f"Missing verse positions: {len(EXPECTED_MISSING)}"
        )
