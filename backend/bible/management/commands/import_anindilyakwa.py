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


SOURCES = {
    "GEN": (1, "02-Genesis.usfm"),
    "JON": (32, "33-Jonah.usfm"),
    "LUK": (42, "48-Luke.usfm"),
    "EPH": (49, "55-Ephesians.usfm"),
    "1TI": (54, "60-1Timothy.usfm"),
    "JAS": (59, "65-James.usfm"),
}

CHAPTER_PATTERN = re.compile(
    r"^\\c\s+(?P<number>\d+)\b"
)

VERSE_PATTERN = re.compile(
    r"^\\v\s+"
    r"(?P<first>\d+)"
    r"(?:-(?P<last>\d+))?"
    r"\s*(?P<text>.*)$"
)

IGNORE_LINE_MARKERS = {
    "id", "ide", "h",
    "toc1", "toc2", "toc3",
    "mt", "mt1", "mt2", "mt3", "mt4",
    "mte", "mte1", "mte2",
    "s", "s1", "s2", "s3", "s4",
    "ms", "ms1", "ms2", "mr",
    "r", "d", "sp", "cl", "cp", "rem",
    "is", "is1", "is2", "ip", "ipi",
    "im", "imi", "iq", "iq1", "iq2",
}


def clean_usfm(text):
    # Remove footnotes, cross-references and figures.
    for marker in ("f", "fe", "x", "fig"):
        text = re.sub(
            rf"\\{marker}\b.*?\\{marker}\*",
            "",
            text,
            flags=re.DOTALL,
        )

    # Retain displayed words while removing word attributes.
    text = re.sub(
        r"\\\+?w\s+([^|\\]*?)(?:\|[^\\]*?)?\\\+?w\*",
        r"\1",
        text,
    )

    # Remove remaining USFM markers while retaining their text.
    text = re.sub(
        r"\\[+A-Za-z0-9-]+\*?",
        "",
        text,
    )

    text = text.replace("\\*", "")
    text = text.replace("~", " ")

    return re.sub(r"\s+", " ", text).strip()


def parse_usfm(path, expected_code):
    segments = {}
    expanded_positions = set()
    chapters_seen = set()
    combined_ranges = 0

    current_chapter = None
    current_first = None
    current_last = None
    fragments = []

    id_code = None

    def save_current_segment():
        nonlocal fragments, combined_ranges

        if current_chapter is None or current_first is None:
            fragments = []
            return

        text = clean_usfm(" ".join(fragments))

        if not text:
            raise CommandError(
                f"{path.name}: empty text at "
                f"{expected_code} "
                f"{current_chapter}:{current_first}"
            )

        key = (
            expected_code,
            current_chapter,
            current_first,
        )

        if key in segments:
            raise CommandError(
                f"{path.name}: duplicate segment {key}"
            )

        segments[key] = {
            "last": current_last,
            "text": text,
        }

        if current_last > current_first:
            combined_ranges += 1

        for number in range(
            current_first,
            current_last + 1,
        ):
            expanded_key = (
                expected_code,
                current_chapter,
                number,
            )

            if expanded_key in expanded_positions:
                raise CommandError(
                    f"{path.name}: overlapping verse "
                    f"{current_chapter}:{number}"
                )

            expanded_positions.add(expanded_key)

        fragments = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        id_match = re.match(
            r"^\\id\s+([A-Z0-9]+)\b",
            line,
            re.IGNORECASE,
        )

        if id_match:
            id_code = id_match.group(1).upper()
            continue

        chapter_match = CHAPTER_PATTERN.match(line)

        if chapter_match:
            save_current_segment()

            current_chapter = int(
                chapter_match.group("number")
            )
            current_first = None
            current_last = None
            chapters_seen.add(current_chapter)
            continue

        verse_match = VERSE_PATTERN.match(line)

        if verse_match:
            save_current_segment()

            if current_chapter is None:
                raise CommandError(
                    f"{path.name}: verse before chapter"
                )

            current_first = int(
                verse_match.group("first")
            )
            current_last = int(
                verse_match.group("last")
                or current_first
            )

            if current_last < current_first:
                raise CommandError(
                    f"{path.name}: invalid range "
                    f"{current_first}-{current_last}"
                )

            fragments = [verse_match.group("text")]
            continue

        if current_first is None:
            continue

        marker_match = re.match(
            r"^\\(?P<marker>[+A-Za-z0-9-]+)\b",
            line,
        )

        if marker_match:
            marker = marker_match.group(
                "marker"
            ).lstrip("+")

            if marker in IGNORE_LINE_MARKERS:
                continue

        # Preserve paragraph and poetry continuations.
        fragments.append(line)

    save_current_segment()

    if id_code != expected_code:
        raise CommandError(
            f"{path.name}: expected ID {expected_code}, "
            f"found {id_code}"
        )

    return {
        "segments": segments,
        "expanded": expanded_positions,
        "chapters": chapters_seen,
        "combined_ranges": combined_ranges,
    }


class Command(BaseCommand):
    help = "Import the Anindilyakwa English Bible portions."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(
                f"Folder not found: {folder}"
            )

        all_segments = {}
        all_expanded = set()
        source_chapters = set()
        combined_range_count = 0

        for code, (position, filename) in SOURCES.items():
            path = folder / filename

            if not path.is_file():
                raise CommandError(
                    f"Source file not found: {path}"
                )

            parsed = parse_usfm(path, code)

            for key, value in parsed["segments"].items():
                if key in all_segments:
                    raise CommandError(
                        f"Duplicate source segment: {key}"
                    )

                all_segments[key] = value

            overlap = all_expanded.intersection(
                parsed["expanded"]
            )

            if overlap:
                raise CommandError(
                    f"Overlapping positions: {sorted(overlap)[:20]}"
                )

            all_expanded.update(parsed["expanded"])

            source_chapters.update(
                (code, chapter)
                for chapter in parsed["chapters"]
            )

            combined_range_count += parsed[
                "combined_ranges"
            ]

        canonical_verses = {}
        canonical_chapters = set()

        for code, (position, filename) in SOURCES.items():
            try:
                book = Book.objects.get(position=position)
            except Book.DoesNotExist as error:
                raise CommandError(
                    f"Canonical book position "
                    f"{position} not found"
                ) from error

            chapters = Chapter.objects.filter(
                book=book
            ).order_by("number")

            for chapter in chapters:
                canonical_chapters.add(
                    (code, chapter.number)
                )

                for verse in Verse.objects.filter(
                    chapter=chapter
                ).order_by("number"):
                    key = (
                        code,
                        chapter.number,
                        verse.number,
                    )
                    canonical_verses[key] = verse

        if source_chapters != canonical_chapters:
            missing = sorted(
                canonical_chapters - source_chapters
            )
            unexpected = sorted(
                source_chapters - canonical_chapters
            )

            raise CommandError(
                "Chapter validation failed:\n"
                f"Missing: {missing[:20]}\n"
                f"Unexpected: {unexpected[:20]}"
            )

        expected_positions = set(canonical_verses)

        if all_expanded != expected_positions:
            missing = sorted(
                expected_positions - all_expanded
            )
            unexpected = sorted(
                all_expanded - expected_positions
            )

            raise CommandError(
                "Verse validation failed:\n"
                f"Missing: {missing[:20]}\n"
                f"Unexpected: {unexpected[:20]}"
            )

        verse_texts = []

        for key, source_segment in all_segments.items():
            canonical_verse = canonical_verses.get(key)

            if canonical_verse is None:
                raise CommandError(
                    f"No canonical verse for {key}"
                )

            verse_texts.append(
                VerseText(
                    verse=canonical_verse,
                    text=source_segment["text"],
                )
            )

        with transaction.atomic():
            version, created = BibleVersion.objects.get_or_create(
                abbreviation="AEB",
                defaults={
                    "name": "Anindilyakwa English Bible",
                    "language": "English",
                    "year": 2021,
                },
            )

            version.name = "Anindilyakwa English Bible"
            version.language = "English"
            version.year = 2021
            version.pdf_filename = "Anindilyakwa.pdf"
            version.description = (
                "Portions of the Holy Bible in English, "
                "written for Anindilyakwa speakers in "
                "Australia to understand. Copyright © 2021 "
                "Bible Society Australia. Licensed under "
                "CC BY-NC-ND 4.0. Combined verse ranges are "
                "stored unchanged at their first canonical "
                "verse position. Source: "
                "https://ebible.org/engaoi"
            )
            version.save()

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            for verse_text in verse_texts:
                verse_text.bible_version = version

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=1000,
            )

        continuation_positions = (
            len(all_expanded) - len(all_segments)
        )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})"
            )
        )
        self.stdout.write(
            f"Books: {len(SOURCES)}"
        )
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Source verse segments: {len(all_segments)}"
        )
        self.stdout.write(
            f"Combined ranges: {combined_range_count}"
        )
        self.stdout.write(
            f"Covered verse positions: {len(all_expanded)}"
        )
        self.stdout.write(
            f"Imported texts: {len(verse_texts)}"
        )
        self.stdout.write(
            "Range continuation positions left empty: "
            f"{continuation_positions}"
        )
