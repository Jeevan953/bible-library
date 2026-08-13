import hashlib
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


BOOK_CODES = (
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
    "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
    "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
    "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
    "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO",
    "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI",
    "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN",
    "3JN", "JUD", "REV",
)

BOOK_POSITIONS = {
    code: position
    for position, code in enumerate(BOOK_CODES, start=1)
}
POSITION_CODES = {
    position: code
    for code, position in BOOK_POSITIONS.items()
}

TEXT_MARKERS = {
    "p", "q1", "q2", "q3", "qm1", "qm2", "qr", "qc",
    "li1", "li2", "li3", "li4",
    "pm", "pmc", "pmo", "m", "mi", "pi1", "pc", "pr",
    "nb", "b",
}

IGNORED_MARKERS = {
    "id", "h", "toc1", "toc2", "toc3", "mt", "mt1", "mt2",
    "c", "cl", "s1", "s2", "ms", "ms1", "mr", "d", "sp", "qa",
}

INLINE_MARKERS = {"sc", "tl"}

EXPECTED_SOURCE_RECORDS = 31102
EXPECTED_CHAPTERS = 1189
EXPECTED_CANONICAL_TEXTS = 31102
EXPECTED_TOTAL_FOOTNOTES = 897
EXPECTED_VERSE_FOOTNOTES = 893
EXPECTED_OUTSIDE_FOOTNOTES = 4
EXPECTED_CANONICAL_SHA256 = (
    "b34bd8ece2841372704bbe5bb6898c058f797501ba10313552c2debc57352726"
)

VERSION_NAME = "Open Indian Tamil Contemporary Version"
VERSION_ABBREVIATION = "OTCV"
VERSION_LANGUAGE = "Tamil"
VERSION_YEAR = 2022
VERSION_DESCRIPTION = (
    "Adapted database representation of the Open Indian Tamil Contemporary "
    "Version. Original-work notice: Biblica® திறந்தநிலை தமிழ் சமகால "
    "பதிப்பு™ — பதிப்புரிமை © 2005, 2020, 2022 Biblica, Inc. "
    "Biblica® Open Indian Tamil Contemporary Version™ — Copyright © 2005, "
    "2020, 2022 by Biblica, Inc. ‘Biblica’ is a trademark registered in the "
    "United States Patent and Trademark Office by Biblica, Inc. Used with "
    "permission. The original work by Biblica, Inc. is available for free "
    "at https://www.biblica.com and https://open.bible. Changes in this "
    "adaptation: USFM layout, section headings, Psalm superscriptions, and "
    "footnotes are omitted; Psalm 1:1-2 is split into canonical verses 1 "
    "and 2; and 3 John 1:15 is merged into canonical verse 14. This adapted "
    "representation is made available under the Creative Commons "
    "Attribution-ShareAlike 4.0 International License: "
    "https://creativecommons.org/licenses/by-sa/4.0/."
)


def reference(position):
    book_position, chapter, verse = position
    code = POSITION_CODES.get(book_position, f"book-{book_position}")
    return f"{code} {chapter}:{verse}"


def collect_records(path, book_code):
    records = []
    chapters = set()
    chapter = None
    current = None
    source_id = None

    def finish():
        nonlocal current
        if current is not None:
            records.append(current)
            current = None

    text = path.read_text(encoding="utf-8-sig", errors="strict")
    total_footnotes = len(re.findall(r"\\f(?:\s|$)", text))

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()

        id_match = re.match(r"^\\id\s+(\S+)", line)
        if id_match and source_id is None:
            source_id = id_match.group(1).upper()

        chapter_match = re.match(r"^\\c\s+(\S+)", line)
        if chapter_match:
            finish()
            chapter_token = chapter_match.group(1)
            if not chapter_token.isdigit():
                raise CommandError(
                    f"Non-numeric chapter token {chapter_token!r} "
                    f"in {path.name}:{line_number}."
                )
            chapter = int(chapter_token)
            chapters.add(chapter)
            continue

        verse_match = re.match(r"^\\v\s+(\S+)", line)
        if verse_match:
            if chapter is None:
                raise CommandError(
                    f"Verse before chapter in {path.name}:{line_number}."
                )
            finish()
            current = {
                "book_code": book_code,
                "chapter": chapter,
                "verse_token": verse_match.group(1),
                "line_number": line_number,
                "lines": [line],
            }
            continue

        if current is not None:
            current["lines"].append(line)

    finish()

    if source_id != book_code:
        raise CommandError(
            f"Expected \\id {book_code} in {path.name}, found {source_id!r}."
        )

    return records, chapters, total_footnotes


def read_source(source_dir):
    if not source_dir.is_dir():
        raise CommandError(f"Source directory does not exist: {source_dir}")

    expected_names = {f"{code}.usfm" for code in BOOK_CODES}
    actual_names = {path.name for path in source_dir.glob("*.usfm")}
    missing_files = sorted(expected_names - actual_names)
    extra_files = sorted(actual_names - expected_names)

    if missing_files or extra_files:
        details = []
        if missing_files:
            details.append(f"missing files: {', '.join(missing_files)}")
        if extra_files:
            details.append(f"extra files: {', '.join(extra_files)}")
        raise CommandError("Invalid OTCV source set; " + "; ".join(details))

    source = {}
    chapter_positions = set()
    total_footnotes = 0

    for book_code in BOOK_CODES:
        path = source_dir / f"{book_code}.usfm"
        records, chapters, footnotes = collect_records(path, book_code)
        total_footnotes += footnotes
        book_position = BOOK_POSITIONS[book_code]

        for chapter in chapters:
            chapter_positions.add((book_position, chapter))

        for record in records:
            key = (
                book_code,
                record["chapter"],
                record["verse_token"],
            )
            if key in source:
                raise CommandError(
                    f"Duplicate source reference: "
                    f"{book_code} {record['chapter']}:"
                    f"{record['verse_token']}"
                )
            source[key] = record

    if len(source) != EXPECTED_SOURCE_RECORDS:
        raise CommandError(
            f"Expected {EXPECTED_SOURCE_RECORDS} source records, "
            f"found {len(source)}."
        )

    if len(chapter_positions) != EXPECTED_CHAPTERS:
        raise CommandError(
            f"Expected {EXPECTED_CHAPTERS} chapters, "
            f"found {len(chapter_positions)}."
        )

    if total_footnotes != EXPECTED_TOTAL_FOOTNOTES:
        raise CommandError(
            f"Expected {EXPECTED_TOTAL_FOOTNOTES} total footnotes, "
            f"found {total_footnotes}."
        )

    return source, chapter_positions, total_footnotes


def normalize_lines(lines, stats):
    combined = "\n".join(lines)
    combined, removed = re.subn(
        r"\\f\s.*?\\f\*",
        " ",
        combined,
        flags=re.DOTALL,
    )
    stats["footnotes_removed"] += removed

    chunks = []

    for raw_line in combined.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        verse_match = re.match(r"^\\v\s+\S+\s*(.*)$", line)
        if verse_match:
            content = verse_match.group(1).strip()
            if content:
                chunks.append(content)
            continue

        marker_match = re.match(
            r"^\\([A-Za-z][A-Za-z0-9]*)(?:\*)?\s*(.*)$",
            line,
        )
        if marker_match:
            marker, content = marker_match.groups()
            content = content.strip()
            if marker in TEXT_MARKERS or marker in INLINE_MARKERS:
                if content:
                    chunks.append(content)
            elif marker in IGNORED_MARKERS:
                continue
            else:
                stats["unknown_markers"][marker] += 1
            continue

        chunks.append(line)

    text = " ".join(chunks)
    text = re.sub(r"\\(?:sc|tl)\*?", "", text)

    for marker in re.findall(
        r"\\([A-Za-z][A-Za-z0-9]*)(?:\*)?",
        text,
    ):
        stats["remaining_markers"][marker] += 1

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def split_psalm_1_1_2(lines, stats):
    verse_one_lines = [lines[0]]
    verse_two_lines = []
    second_part_started = False

    for line in lines[1:]:
        if (
            not second_part_started
            and re.match(r"^\\q1\s+\S", line.strip())
        ):
            second_part_started = True

        if second_part_started:
            verse_two_lines.append(line)
        else:
            verse_one_lines.append(line)

    verse_one = normalize_lines(verse_one_lines, stats)
    verse_two = normalize_lines(verse_two_lines, stats)

    if not verse_one or not verse_two:
        raise CommandError("Could not split Psalm 1:1-2 safely.")

    return verse_one, verse_two


def canonicalize(source, total_footnotes):
    generated = {}
    stats = {
        "footnotes_removed": 0,
        "unknown_markers": Counter(),
        "remaining_markers": Counter(),
    }

    for key, record in source.items():
        book_code, chapter, verse_token = key
        book_position = BOOK_POSITIONS[book_code]

        if key == ("PSA", 1, "1-2"):
            verse_one, verse_two = split_psalm_1_1_2(
                record["lines"], stats
            )
            generated[(book_position, 1, 1)] = verse_one
            generated[(book_position, 1, 2)] = verse_two
            continue

        if key == ("3JN", 1, "15"):
            continue

        if not verse_token.isdigit():
            raise CommandError(
                f"Unhandled verse token: "
                f"{book_code} {chapter}:{verse_token}"
            )

        verse_number = int(verse_token)
        text = normalize_lines(record["lines"], stats)

        if key == ("3JN", 1, "14"):
            verse_15 = source.get(("3JN", 1, "15"))
            if verse_15 is None:
                raise CommandError("Missing 3 John 1:15 source record.")
            text_15 = normalize_lines(verse_15["lines"], stats)
            text = f"{text} {text_15}".strip()

        position = (book_position, chapter, verse_number)
        if position in generated:
            raise CommandError(
                f"Duplicate canonical position: {reference(position)}"
            )
        generated[position] = text

    if len(generated) != EXPECTED_CANONICAL_TEXTS:
        raise CommandError(
            f"Expected {EXPECTED_CANONICAL_TEXTS} canonical texts, "
            f"generated {len(generated)}."
        )

    empty_positions = [
        position for position, text in generated.items() if not text
    ]
    if empty_positions:
        sample = ", ".join(reference(item) for item in empty_positions[:10])
        raise CommandError(f"Empty normalized verse texts: {sample}")

    replacement_characters = sum(
        text.count("\ufffd") for text in generated.values()
    )
    if replacement_characters:
        raise CommandError(
            f"Found {replacement_characters} UTF-8 replacement characters."
        )

    if stats["unknown_markers"]:
        details = ", ".join(
            f"\\{marker}={count}"
            for marker, count in stats["unknown_markers"].most_common()
        )
        raise CommandError(f"Unknown leading USFM markers: {details}")

    if stats["remaining_markers"]:
        details = ", ".join(
            f"\\{marker}={count}"
            for marker, count in stats["remaining_markers"].most_common()
        )
        raise CommandError(f"Remaining inline USFM markers: {details}")

    if stats["footnotes_removed"] != EXPECTED_VERSE_FOOTNOTES:
        raise CommandError(
            f"Expected to remove {EXPECTED_VERSE_FOOTNOTES} verse "
            f"footnotes, removed {stats['footnotes_removed']}."
        )

    outside_footnotes = total_footnotes - stats["footnotes_removed"]
    if outside_footnotes != EXPECTED_OUTSIDE_FOOTNOTES:
        raise CommandError(
            f"Expected {EXPECTED_OUTSIDE_FOOTNOTES} outside-verse "
            f"footnotes, found {outside_footnotes}."
        )

    digest = hashlib.sha256()
    for position, text in sorted(generated.items()):
        book_position, chapter, verse = position
        book_code = POSITION_CODES[book_position]
        digest.update(
            f"{book_code}\t{chapter}\t{verse}\t{text}\n".encode("utf-8")
        )
    canonical_sha256 = digest.hexdigest()

    if canonical_sha256 != EXPECTED_CANONICAL_SHA256:
        raise CommandError(
            "Canonical SHA256 mismatch. "
            f"Expected {EXPECTED_CANONICAL_SHA256}, "
            f"found {canonical_sha256}."
        )

    return generated, stats, outside_footnotes, canonical_sha256


class Command(BaseCommand):
    help = (
        "Import the CC BY-SA 4.0 Open Indian Tamil Contemporary "
        "Version USFM files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source_dir",
            type=Path,
            help="Directory containing the 66 OTCV USFM files.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate sources and canonical mappings without writing.",
        )

    def handle(self, *args, **options):
        source_dir = options["source_dir"].expanduser().resolve()
        dry_run = options["dry_run"]

        self.stdout.write("OTCV IMPORT VALIDATION")
        self.stdout.write(f"Source: {source_dir}")
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'IMPORT'}")

        source, chapter_positions, total_footnotes = read_source(source_dir)
        generated, stats, outside_footnotes, canonical_sha256 = canonicalize(
            source, total_footnotes
        )

        verse_objects = {}
        duplicate_database_positions = []
        for verse in Verse.objects.select_related("chapter__book").all():
            position = (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            )
            if position in verse_objects:
                duplicate_database_positions.append(position)
            verse_objects[position] = verse

        if duplicate_database_positions:
            sample = ", ".join(
                reference(item) for item in duplicate_database_positions[:10]
            )
            raise CommandError(
                f"Duplicate canonical database positions: {sample}"
            )

        database_positions = set(verse_objects)
        generated_positions = set(generated)
        missing_positions = sorted(database_positions - generated_positions)
        extra_positions = sorted(generated_positions - database_positions)

        if missing_positions or extra_positions:
            details = []
            if missing_positions:
                sample = ", ".join(
                    reference(item) for item in missing_positions[:10]
                )
                details.append(
                    f"missing={len(missing_positions)} ({sample})"
                )
            if extra_positions:
                sample = ", ".join(
                    reference(item) for item in extra_positions[:10]
                )
                details.append(f"extra={len(extra_positions)} ({sample})")
            raise CommandError(
                "OTCV canonical positions do not match the database: "
                + "; ".join(details)
            )

        self.stdout.write(f"Raw source records: {len(source)}")
        self.stdout.write(f"Books: {len(BOOK_CODES)}")
        self.stdout.write(f"Chapters: {len(chapter_positions)}")
        self.stdout.write(f"Canonical verse texts: {len(generated)}")
        self.stdout.write(
            f"Verse footnotes removed: {stats['footnotes_removed']}"
        )
        self.stdout.write(
            f"Non-verse footnotes omitted: {outside_footnotes}"
        )
        self.stdout.write(f"Canonical SHA256: {canonical_sha256}")
        self.stdout.write("Missing positions: 0")
        self.stdout.write("Extra positions: 0")
        self.stdout.write("Remaining USFM markers: 0")
        self.stdout.write("License: CC BY-SA 4.0")
        self.stdout.write(
            "Adaptation: formatting, headings, superscriptions, and "
            "footnotes omitted; Psalm 1 and 3 John canonicalized."
        )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run passed. No database records were changed."
                )
            )
            return

        with transaction.atomic():
            version = (
                BibleVersion.objects.select_for_update()
                .filter(abbreviation=VERSION_ABBREVIATION)
                .first()
            )

            created = version is None
            if created:
                version = BibleVersion.objects.create(
                    name=VERSION_NAME,
                    abbreviation=VERSION_ABBREVIATION,
                    language=VERSION_LANGUAGE,
                    year=VERSION_YEAR,
                    description=VERSION_DESCRIPTION,
                    pdf_filename="",
                )
            else:
                version.name = VERSION_NAME
                version.language = VERSION_LANGUAGE
                version.year = VERSION_YEAR
                version.description = VERSION_DESCRIPTION
                version.save(
                    update_fields=[
                        "name", "language", "year", "description"
                    ]
                )

            previous_count = VerseText.objects.filter(
                bible_version=version
            ).count()
            VerseText.objects.filter(bible_version=version).delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse=verse_objects[position],
                        text=text,
                    )
                    for position, text in sorted(generated.items())
                ],
                batch_size=1000,
            )

            imported_count = VerseText.objects.filter(
                bible_version=version
            ).count()
            if imported_count != EXPECTED_CANONICAL_TEXTS:
                raise CommandError(
                    f"Expected {EXPECTED_CANONICAL_TEXTS} imported texts, "
                    f"found {imported_count}; transaction rolled back."
                )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {VERSION_NAME} ({VERSION_ABBREVIATION})"
            )
        )
        self.stdout.write(f"Previous verse texts: {previous_count}")
        self.stdout.write(f"Imported verse texts: {imported_count}")
        self.stdout.write(
            self.style.SUCCESS("OTCV import completed successfully.")
        )
