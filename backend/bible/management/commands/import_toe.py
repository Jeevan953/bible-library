import hashlib
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


FILES = {
    1: "02-GENengoke.usfm",
    2: "03-EXOengoke.usfm",
    3: "04-LEVengoke.usfm",
    4: "05-NUMengoke.usfm",
    5: "06-DEUengoke.usfm",
}

BOOK_NAMES = {
    1: "Genesis",
    2: "Exodus",
    3: "Leviticus",
    4: "Numbers",
    5: "Deuteronomy",
}

EXPECTED_HASHES = {
    "02-GENengoke.usfm": "f4c65918c22975534c7f221f4b14c26eabfd7ffd3f6b127581dab8e67b169448",
    "03-EXOengoke.usfm": "11417fc99c172e4c96316315c5b3b11fc99ff0c135ca58df6cfe08848fc3a622",
    "04-LEVengoke.usfm": "8021ac7544479612a87fd2e964f39cf1c90a1630038bf3b9bc37ccb5c87f5359",
    "05-NUMengoke.usfm": "3b878b6f82de3f0fa2521e5a52ce65c287444f26455e923f85c858c7c019978f",
    "06-DEUengoke.usfm": "3c004322ad25dea7471b62ae3b8c80e56e5fdee2c26065dd0cd695f9762a85f1",
}

MARKER_PATTERN = re.compile(r"\\[A-Za-z][A-Za-z0-9]*\*?")


def reference(position):
    book, chapter, verse = position
    return f"{BOOK_NAMES[book]} {chapter}:{verse}"


def normalize_text(text):
    text = re.sub(r"\\f\b.*?\\f\*", "", text, flags=re.DOTALL)
    text = re.sub(r"\\va\s+.*?\\va\*", "", text)
    text = re.sub(
        r"\\(?:it|add|bd|bdit|em|k|nd|ord|pn|qt|sc|sig|sls|tl|wj)\*?",
        "",
        text,
    )
    return " ".join(text.split()).strip()


def canonical_reference(book, chapter, verse):
    if book == 1 and chapter == 32:
        if verse == 1:
            return 1, 31, 55
        return 1, 32, verse - 1

    if book == 2 and chapter == 7 and 26 <= verse <= 29:
        return 2, 8, verse - 25
    if book == 2 and chapter == 8:
        return 2, 8, verse + 4
    if book == 2 and chapter == 20 and 14 <= verse <= 23:
        return 2, 20, verse + 3
    if book == 2 and chapter == 21 and verse == 37:
        return 2, 22, 1
    if book == 2 and chapter == 22:
        return 2, 22, verse + 1

    if book == 3 and chapter == 5 and 20 <= verse <= 26:
        return 3, 6, verse - 19
    if book == 3 and chapter == 6:
        return 3, 6, verse + 7

    if book == 4 and chapter == 17 and 1 <= verse <= 15:
        return 4, 16, verse + 35
    if book == 4 and chapter == 17 and 16 <= verse <= 28:
        return 4, 17, verse - 15
    if book == 4 and chapter == 30 and verse == 1:
        return 4, 29, 40
    if book == 4 and chapter == 30 and 2 <= verse <= 17:
        return 4, 30, verse - 1

    if book == 5 and chapter == 5 and 18 <= verse <= 30:
        return 5, 5, verse + 3
    if book == 5 and chapter == 13 and verse == 1:
        return 5, 12, 32
    if book == 5 and chapter == 13 and 2 <= verse <= 19:
        return 5, 13, verse - 1
    if book == 5 and chapter == 23 and verse == 1:
        return 5, 22, 30
    if book == 5 and chapter == 23 and 2 <= verse <= 26:
        return 5, 23, verse - 1
    if book == 5 and chapter == 28 and verse == 69:
        return 5, 29, 1
    if book == 5 and chapter == 29:
        return 5, 29, verse + 1

    return book, chapter, verse


def read_source(source_dir):
    source = {}

    for book_position, filename in FILES.items():
        path = source_dir / filename
        if not path.is_file():
            raise CommandError(f"Missing source file: {path}")

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = EXPECTED_HASHES[filename]
        if digest != expected:
            raise CommandError(
                f"Source checksum mismatch for {filename}:\n"
                f"expected {expected}\nfound    {digest}"
            )

        chapter = None
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(),
            start=1,
        ):
            line = raw_line.strip()

            chapter_match = re.match(r"^\\c\s+(\d+)\b", line)
            if chapter_match:
                chapter = int(chapter_match.group(1))
                continue

            verse_match = re.match(r"^\\v\s+(\d+)\s*(.*)$", line)
            if not verse_match:
                continue

            if chapter is None:
                raise CommandError(
                    f"{path}:{line_number}: verse before chapter"
                )

            verse = int(verse_match.group(1))
            text = verse_match.group(2).strip()
            position = (book_position, chapter, verse)

            if position in source:
                raise CommandError(
                    f"Duplicate source reference: {reference(position)}"
                )
            if not text:
                raise CommandError(
                    f"Empty source text: {reference(position)}"
                )

            source[position] = text

    if len(source) != 5848:
        raise CommandError(
            f"Expected 5,848 raw source records; found {len(source)}"
        )

    return source


def canonicalize(source):
    source = dict(source)
    generated = {}
    origins = {}

    def emit(position, text, origin):
        cleaned = normalize_text(text)
        if not cleaned:
            raise CommandError(
                f"Empty normalized text: {reference(position)}"
            )
        markers = MARKER_PATTERN.findall(cleaned)
        if markers:
            raise CommandError(
                f"Unremoved markers at {reference(position)}: {markers}"
            )
        if position in generated:
            raise CommandError(
                f"Duplicate canonical position {reference(position)}; "
                f"origins: {origins[position]} and {origin}"
            )
        generated[position] = cleaned
        origins[position] = origin

    exodus_zero = source.pop((2, 16, 0))
    source[(2, 16, 3)] = (
        source[(2, 16, 3)].rstrip() + " " + exodus_zero.lstrip()
    )

    numbers_fragment = source.pop((4, 25, 19))
    source[(4, 26, 1)] = (
        numbers_fragment.rstrip() + " " + source[(4, 26, 1)].lstrip()
    )

    exodus_combined = source.pop((2, 20, 13))
    exodus_parts = re.split(
        r"\s*\\va\s+\d+\s*\\va\*\s*",
        exodus_combined,
    )
    if len(exodus_parts) != 4:
        raise CommandError(
            "Expected Exodus 20:13 to split into four verses; "
            f"found {len(exodus_parts)} parts"
        )
    for verse_number, text in enumerate(exodus_parts, start=13):
        emit(
            (2, 20, verse_number),
            text,
            "Exodus 20:13 split",
        )

    deuteronomy_combined = source.pop((5, 5, 17))
    expected_deuteronomy = (
        "Thou shalt not kill life, nor commit adultery, "
        "nor steal, nor bear false witness against thy neighbour."
    )
    if deuteronomy_combined != expected_deuteronomy:
        raise CommandError(
            "Unexpected Deuteronomy 5:17 wording:\n"
            f"{deuteronomy_combined}"
        )

    deuteronomy_parts = [
        "Thou shalt not kill life,",
        "nor commit adultery,",
        "nor steal,",
        "nor bear false witness against thy neighbour.",
    ]
    for verse_number, text in enumerate(deuteronomy_parts, start=17):
        emit(
            (5, 5, verse_number),
            text,
            "Deuteronomy 5:17 split",
        )

    for source_position, text in sorted(source.items()):
        emit(
            canonical_reference(*source_position),
            text,
            reference(source_position),
        )

    if len(generated) != 5852:
        raise CommandError(
            f"Expected 5,852 canonical positions; found {len(generated)}"
        )

    return generated


class Command(BaseCommand):
    help = "Import the public-domain Targum Onkelos Etheridge USFM files."

    def add_arguments(self, parser):
        parser.add_argument(
            "source_dir",
            type=Path,
            help="Directory containing the five engoke USFM files.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate sources and canonical mappings without writing.",
        )

    def handle(self, *args, **options):
        source_dir = options["source_dir"].expanduser().resolve()
        dry_run = options["dry_run"]

        self.stdout.write("TOE IMPORT VALIDATION")
        self.stdout.write(f"Source: {source_dir}")
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'IMPORT'}")

        source = read_source(source_dir)
        generated = canonicalize(source)

        verse_objects = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.filter(
                chapter__book__position__range=(1, 5)
            ).select_related("chapter__book")
        }

        canonical_positions = set(verse_objects)
        generated_positions = set(generated)
        missing = sorted(canonical_positions - generated_positions)
        extra = sorted(generated_positions - canonical_positions)

        if missing or extra:
            details = []
            if missing:
                details.append(
                    "Missing: "
                    + ", ".join(reference(item) for item in missing[:20])
                )
            if extra:
                details.append(
                    "Extra: "
                    + ", ".join(reference(item) for item in extra[:20])
                )
            raise CommandError("Canonical mismatch. " + " | ".join(details))

        if len(canonical_positions) != 5852:
            raise CommandError(
                "Expected 5,852 canonical database positions in the "
                f"Pentateuch; found {len(canonical_positions)}"
            )

        chapter_count = len(
            {(book, chapter) for book, chapter, _ in generated_positions}
        )

        self.stdout.write(f"Raw source records: {len(source)}")
        self.stdout.write(f"Books: 5")
        self.stdout.write(f"Chapters: {chapter_count}")
        self.stdout.write(f"Canonical verse texts: {len(generated)}")
        self.stdout.write("Missing positions: 0")
        self.stdout.write("Extra positions: 0")
        self.stdout.write("Remaining USFM markers: 0")

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
                .filter(abbreviation="TOE")
                .first()
            )

            created = version is None
            if created:
                version = BibleVersion.objects.create(
                    name="Targum Onkelos Etheridge",
                    abbreviation="TOE",
                    language="English",
                    year=1865,
                )
            else:
                version.name = "Targum Onkelos Etheridge"
                version.language = "English"
                version.year = 1865
                version.save(update_fields=["name", "language", "year"])

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
            if imported_count != 5852:
                raise CommandError(
                    f"Import verification failed: found {imported_count} "
                    "TOE verse texts"
                )

        action = "Created" if created else "Updated"
        self.stdout.write(f"{action}: {version.name} ({version.abbreviation})")
        self.stdout.write(f"Previous verse texts: {previous_count}")
        self.stdout.write(f"Imported verse texts: {imported_count}")
        self.stdout.write(
            self.style.SUCCESS("TOE import completed successfully.")
        )
