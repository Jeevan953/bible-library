import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Book,
    Verse,
    VerseText,
)


VERSION_NAME = (
    "Open Indian Tamil Contemporary Version"
)
ABBREVIATION = "OTCV"
LANGUAGE = "Tamil"
YEAR = 2022

DEFAULT_SOURCE_DIR = Path(
    "data/Open Indian Tamil Contemporary Version"
)

BOOK_CODES = """
GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA
1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO
ECC SNG ISA JER LAM EZK DAN HOS JOL AMO
OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT
MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP
COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE
2PE 1JN 2JN 3JN JUD REV
""".split()

EXCLUDED_ELEMENTS = {
    "note",
    "ref",
    "figure",
    "sidebar",
}

MARKER_PATTERN = re.compile(
    r"([1-3]?[A-Z]{2,3}) "
    r"(\d+):([0-9]+(?:-[0-9]+)?)"
)

PSALM_BOUNDARY = (
    "யெகோவாவினுடைய சட்டத்திலே"
)

PSALM_ONE_ENDING = (
    "பரிகாசக்காரருடன் உட்காராமல்,"
)

DESCRIPTION = (
    "Open Indian Tamil Contemporary Version "
    "(OTCV), completed in 2022. Original work "
    "copyright © 2005, 2020, 2022 by Biblica, "
    "Inc. The original work by Biblica, Inc. is "
    "available for free at https://www.biblica.com "
    "and https://open.bible. Licensed under the "
    "Creative Commons Attribution-ShareAlike 4.0 "
    "International License (CC BY-SA 4.0): "
    "https://creativecommons.org/licenses/by-sa/4.0/. "
    "This database presentation is made available "
    "under the same license. Introductions, "
    "footnotes, cross-references, figures, and "
    "sidebars are excluded from verse text. "
    "Versification was normalized for this "
    "application: bridged Psalms 1:1-2 was split "
    "at its poetic and semantic boundary, and "
    "source 3 John 1:15 was combined with canonical "
    "3 John 1:14."
)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def clean_text(text):
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_usx(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise CommandError(
            f"Invalid XML in {path}: {error}"
        ) from error

    fragments = {}
    active = None

    def append(text):
        if active is not None and text:
            fragments.setdefault(
                active,
                [],
            ).append(text)

    def walk(element):
        nonlocal active

        name = local_name(element.tag)

        if name in EXCLUDED_ELEMENTS:
            return

        if name == "verse":
            sid = element.get("sid")
            eid = element.get("eid")

            if sid:
                match = MARKER_PATTERN.fullmatch(
                    sid.strip()
                )

                if not match:
                    raise CommandError(
                        f"Invalid verse marker "
                        f"{sid!r} in {path}"
                    )

                code, chapter, marker = (
                    match.groups()
                )

                active = (
                    code,
                    int(chapter),
                    marker,
                )

                if active in fragments:
                    raise CommandError(
                        f"Duplicate verse marker "
                        f"{sid!r} in {path}"
                    )

                fragments[active] = []

            elif eid:
                active = None

            return

        append(element.text)

        for child in element:
            walk(child)
            append(child.tail)

    walk(root)

    return {
        key: clean_text("".join(parts))
        for key, parts in fragments.items()
    }


def load_source_texts(source_dir):
    release_dir = source_dir / "release"
    metadata_path = source_dir / "metadata.xml"
    license_path = source_dir / "license.xml"

    required = [
        release_dir,
        metadata_path,
        license_path,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise CommandError(
            "Missing required source paths: "
            + ", ".join(missing)
        )

    metadata = metadata_path.read_text(
        encoding="utf-8"
    )
    license_text = license_path.read_text(
        encoding="utf-8"
    )

    required_metadata = [
        "Open Indian Tamil Contemporary Version",
        "<abbreviation>OTCV</abbreviation>",
        "<iso>tam</iso>",
        "Creative Commons "
        "Attribution-ShareAlike 4.0",
        "Copyright © 2005, 2020, 2022 "
        "by Biblica, Inc.",
    ]

    for expected in required_metadata:
        if expected not in metadata:
            raise CommandError(
                "Expected metadata text was not "
                f"found: {expected!r}"
            )

    if 'id="032ec262506b719f"' not in (
        license_text
    ):
        raise CommandError(
            "Unexpected OTCV license identifier"
        )

    usx_paths = sorted(
        release_dir.rglob("*.usx")
    )

    if len(usx_paths) != 66:
        raise CommandError(
            "Expected 66 USX files, found "
            f"{len(usx_paths)}"
        )

    raw_texts = {}

    for usx_path in usx_paths:
        extracted = extract_usx(usx_path)
        overlap = set(raw_texts) & set(extracted)

        if overlap:
            raise CommandError(
                "Duplicate source markers across "
                f"USX files: {sorted(overlap)[:10]}"
            )

        raw_texts.update(extracted)

    if len(raw_texts) != 31102:
        raise CommandError(
            "Expected 31,102 source markers, "
            f"found {len(raw_texts):,}"
        )

    return raw_texts


def build_normalized_texts(
    raw_texts,
    code_to_position,
):
    normalized = {}
    third_john_15_text = None

    for (
        code,
        chapter,
        marker,
    ), text in raw_texts.items():
        if not text:
            raise CommandError(
                "Blank source text at "
                f"{code} {chapter}:{marker}"
            )

        if (
            code,
            chapter,
            marker,
        ) == (
            "PSA",
            1,
            "1-2",
        ):
            before, separator, after = (
                text.partition(PSALM_BOUNDARY)
            )

            if not separator:
                raise CommandError(
                    "Could not find the expected "
                    "Psalms 1:1-2 split boundary"
                )

            verse_one = before.strip()
            verse_two = clean_text(
                separator + after
            )

            if not verse_one.endswith(
                PSALM_ONE_ENDING
            ):
                raise CommandError(
                    "Unexpected Psalms 1:1 ending"
                )

            normalized[
                (
                    code_to_position["PSA"],
                    1,
                    1,
                )
            ] = verse_one

            normalized[
                (
                    code_to_position["PSA"],
                    1,
                    2,
                )
            ] = verse_two

            continue

        if (
            code,
            chapter,
            marker,
        ) == (
            "3JN",
            1,
            "15",
        ):
            third_john_15_text = text
            continue

        try:
            verse_number = int(marker)
        except ValueError as error:
            raise CommandError(
                "Unsupported bridged marker: "
                f"{code} {chapter}:{marker}"
            ) from error

        if code not in code_to_position:
            raise CommandError(
                f"Unsupported book code: {code}"
            )

        position = (
            code_to_position[code],
            chapter,
            verse_number,
        )

        if position in normalized:
            raise CommandError(
                "Duplicate normalized position: "
                f"{position}"
            )

        normalized[position] = text

    if not third_john_15_text:
        raise CommandError(
            "Source 3 John 1:15 was not found"
        )

    third_john_14 = (
        code_to_position["3JN"],
        1,
        14,
    )

    if third_john_14 not in normalized:
        raise CommandError(
            "Source 3 John 1:14 was not found"
        )

    normalized[third_john_14] = clean_text(
        normalized[third_john_14]
        + " "
        + third_john_15_text
    )

    return normalized


class Command(BaseCommand):
    help = (
        "Import the Open Indian Tamil "
        "Contemporary Version from its DBL USX "
        "release bundle."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source_dir",
            nargs="?",
            type=Path,
            default=DEFAULT_SOURCE_DIR,
        )

    def handle(self, *args, **options):
        source_dir = options["source_dir"]

        if not source_dir.is_dir():
            raise CommandError(
                f"Source directory not found: "
                f"{source_dir}"
            )

        books = list(
            Book.objects.order_by(
                "position"
            ).values_list(
                "position",
                "name",
            )
        )

        if len(books) != 66:
            raise CommandError(
                "Expected 66 canonical books, "
                f"found {len(books)}"
            )

        if len(BOOK_CODES) != 66:
            raise CommandError(
                "Internal book-code mapping is "
                "not complete"
            )

        code_to_position = {
            code: position
            for code, (
                position,
                book_name,
            ) in zip(
                BOOK_CODES,
                books,
            )
        }

        raw_texts = load_source_texts(
            source_dir
        )

        normalized = build_normalized_texts(
            raw_texts,
            code_to_position,
        )

        canonical_verses = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.select_related(
                "chapter__book"
            )
        }

        canonical_positions = set(
            canonical_verses
        )
        source_positions = set(normalized)

        missing = sorted(
            canonical_positions - source_positions
        )
        extra = sorted(
            source_positions - canonical_positions
        )

        if missing or extra:
            raise CommandError(
                "Canonical position mismatch. "
                f"Missing: {missing[:20]}; "
                f"extra: {extra[:20]}"
            )

        if len(normalized) != 31102:
            raise CommandError(
                "Expected 31,102 normalized verse "
                f"texts, found {len(normalized):,}"
            )

        for position, text in normalized.items():
            if not text:
                raise CommandError(
                    f"Blank text at {position}"
                )

            if "\ufffd" in text:
                raise CommandError(
                    "Replacement character found "
                    f"at {position}"
                )

            if re.search(r"<[^>]+>", text):
                raise CommandError(
                    "HTML/XML marker found at "
                    f"{position}"
                )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.update_or_create(
                    abbreviation=ABBREVIATION,
                    defaults={
                        "name": VERSION_NAME,
                        "language": LANGUAGE,
                        "year": YEAR,
                        "description": DESCRIPTION,
                        "pdf_filename": "",
                    },
                )
            )

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            VerseText.objects.bulk_create(
                [
                    VerseText(
                        bible_version=version,
                        verse=canonical_verses[
                            position
                        ],
                        text=text,
                    )
                    for position, text in sorted(
                        normalized.items()
                    )
                ],
                batch_size=1000,
            )

        action = (
            "Created"
            if created
            else "Updated"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {VERSION_NAME} "
                f"({ABBREVIATION})"
            )
        )
        self.stdout.write(
            f"Language: {LANGUAGE}"
        )
        self.stdout.write(
            f"Year: {YEAR}"
        )
        self.stdout.write(
            f"Books: {len(books)}"
        )
        self.stdout.write(
            "Chapters: 1189"
        )
        self.stdout.write(
            "Canonical positions: "
            f"{len(canonical_positions)}"
        )
        self.stdout.write(
            "Imported verse texts: "
            f"{len(normalized)}"
        )
        self.stdout.write(
            "Normalization: split bridged "
            "Psalms 1:1-2"
        )
        self.stdout.write(
            "Normalization: combined source "
            "3 John 1:15 with canonical "
            "3 John 1:14"
        )
        self.stdout.write(
            "License: CC BY-SA 4.0"
        )
        self.stdout.write(
            "Copyright: Copyright © 2005, "
            "2020, 2022 by Biblica, Inc."
        )
        self.stdout.write(
            "PDF: not configured"
        )
