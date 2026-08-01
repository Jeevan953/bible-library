import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


SOURCES = {
    "GEN": (1, "02-Genesis.usfm"),
    "RUT": (8, "08-Ruth.usfm"),
    "EST": (17, "17-Esther.usfm"),
    "MRK": (41, "41-Mark.usfm"),
}

OMITTED_POSITIONS = {
    (41, 15, 28),
}

CHAPTER_PATTERN = re.compile(
    r"^\\c\s+(\d+)\b"
)

VERSE_PATTERN = re.compile(
    r"^\\v\s+(\d+)(?:-(\d+))?\s*(.*)$"
)

REMOVABLE_BLOCK_PATTERN = re.compile(
    r"\\(?:f|fe|x|fig)\s+.*?"
    r"\\(?:f|fe|x|fig)\*",
    re.DOTALL,
)

USFM_MARKER_PATTERN = re.compile(
    r"\\\+?[A-Za-z][A-Za-z0-9]*\*?\s*"
)

HEADING_PATTERN = re.compile(
    r"^\\(?:s\d*|ms\d*|mt\d*|r|cl|d|sp|"
    r"toc\d*|h)\b"
)


def clean_usfm(text):
    text = REMOVABLE_BLOCK_PATTERN.sub(
        " ",
        text,
    )
    text = USFM_MARKER_PATTERN.sub(
        " ",
        text,
    )
    text = text.replace("~", " ")

    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"\s+([,.;:!?])",
        r"\1",
        text,
    )
    text = re.sub(
        r"([“‘(\[])\s+",
        r"\1",
        text,
    )
    text = re.sub(
        r"\s+([”’)\]])",
        r"\1",
        text,
    )

    return text


def parse_file(code, position, path):
    records = []

    current_chapter = None
    current_first = None
    current_last = None
    buffer = []

    def save_segment():
        nonlocal buffer

        if (
            current_chapter is None
            or current_first is None
        ):
            buffer = []
            return

        text = clean_usfm(" ".join(buffer))

        if not text:
            raise CommandError(
                f"{code} {current_chapter}:"
                f"{current_first} has no text"
            )

        if re.search(r"\\[A-Za-z]", text):
            raise CommandError(
                f"{code} {current_chapter}:"
                f"{current_first} contains USFM markers: "
                f"{text[:100]!r}"
            )

        records.append(
            (
                position,
                current_chapter,
                current_first,
                current_last,
                text,
            )
        )

        buffer = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        chapter_match = CHAPTER_PATTERN.match(line)

        if chapter_match:
            save_segment()
            current_chapter = int(
                chapter_match.group(1)
            )
            current_first = None
            current_last = None
            continue

        verse_match = VERSE_PATTERN.match(line)

        if verse_match:
            save_segment()

            current_first = int(
                verse_match.group(1)
            )
            current_last = int(
                verse_match.group(2)
                or current_first
            )
            buffer = [verse_match.group(3)]
            continue

        if current_first is None:
            continue

        if HEADING_PATTERN.match(line):
            continue

        # Retains continuation paragraphs and poetry.
        buffer.append(line)

    save_segment()

    return records


class Command(BaseCommand):
    help = "Import the Barkly Bible portions."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(
                f"Folder not found: {folder}"
            )

        pdf_path = folder.parent / "Barkly.pdf"

        if not pdf_path.is_file():
            raise CommandError(
                f"PDF not found: {pdf_path}"
            )

        records = []

        for code, (position, filename) in (
            SOURCES.items()
        ):
            path = folder / filename

            if not path.is_file():
                raise CommandError(
                    f"Source file not found: {path}"
                )

            records.extend(
                parse_file(
                    code,
                    position,
                    path,
                )
            )

        canonical = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.filter(
                chapter__book__position__in=[
                    position
                    for position, _filename
                    in SOURCES.values()
                ]
            ).select_related(
                "chapter",
                "chapter__book",
            )
        }

        covered_positions = set()
        first_positions = set()
        chapter_positions = set()
        combined_ranges = 0
        range_continuations = 0
        errors = []

        for (
            position,
            chapter,
            first,
            last,
            _text,
        ) in records:
            chapter_positions.add(
                (position, chapter)
            )

            first_key = (
                position,
                chapter,
                first,
            )

            if first_key in first_positions:
                errors.append(
                    f"Duplicate starting position: "
                    f"{first_key}"
                )

            first_positions.add(first_key)

            if last > first:
                combined_ranges += 1
                range_continuations += last - first

            for number in range(first, last + 1):
                key = (
                    position,
                    chapter,
                    number,
                )

                if key in covered_positions:
                    errors.append(
                        f"Overlapping position: {key}"
                    )

                covered_positions.add(key)

        canonical_positions = set(canonical)

        missing_positions = (
            canonical_positions - covered_positions
        )
        extra_positions = (
            covered_positions - canonical_positions
        )

        if missing_positions != OMITTED_POSITIONS:
            errors.append(
                "Unexpected missing positions: "
                f"{sorted(missing_positions)}"
            )

        if extra_positions:
            errors.append(
                "Extra positions: "
                f"{sorted(extra_positions)[:30]}"
            )

        if len(chapter_positions) != 80:
            errors.append(
                f"Expected 80 chapters, "
                f"found {len(chapter_positions)}"
            )

        if len(records) != 2145:
            errors.append(
                f"Expected 2145 source segments, "
                f"found {len(records)}"
            )

        missing_first_positions = (
            first_positions - canonical_positions
        )

        if missing_first_positions:
            errors.append(
                "Segment starting positions not found: "
                f"{sorted(missing_first_positions)[:30]}"
            )

        if errors:
            raise CommandError(
                "Barkly validation failed:\n"
                + "\n".join(errors)
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="BARKLY",
                    defaults={
                        "name": "Barkly Bible Portions",
                        "language": "English",
                    },
                )
            )

            version.name = "Barkly Bible Portions"
            version.language = "English"
            version.pdf_filename = "Barkly.pdf"
            version.description = (
                "Barkly Bible portions containing "
                "Genesis, Ruth, Esther and Mark. "
                "Combined verse ranges are stored at "
                "their first verse position."
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
                        verse=canonical[
                            (
                                position,
                                chapter,
                                first,
                            )
                        ],
                        text=text,
                    )
                    for (
                        position,
                        chapter,
                        first,
                        _last,
                        text,
                    ) in records
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
            f"Books: {len(SOURCES)}"
        )
        self.stdout.write(
            f"Chapters: {len(chapter_positions)}"
        )
        self.stdout.write(
            f"Source verse segments: {len(records)}"
        )
        self.stdout.write(
            f"Combined ranges: {combined_ranges}"
        )
        self.stdout.write(
            f"Covered verse positions: "
            f"{len(covered_positions)}"
        )
        self.stdout.write(
            f"Imported texts: {len(records)}"
        )
        self.stdout.write(
            "Range continuation positions left empty: "
            f"{range_continuations}"
        )
        self.stdout.write(
            f"Missing source positions: "
            f"{len(missing_positions)}"
        )
