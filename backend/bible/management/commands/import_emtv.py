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


VERSION_NAME = "English Majority Text Version"
ABBREVIATION = "EMTV"
LANGUAGE = "English"
YEAR = 2014

DEFAULT_SOURCE_DIR = Path(
    "data/English Majority Text Version"
)

BOOK_CODES = """
MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH
PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS
1PE 2PE 1JN 2JN 3JN JUD REV
""".split()

EXCLUDED_ELEMENTS = {
    "note",
    "ref",
    "figure",
    "sidebar",
}

MARKER_PATTERN = re.compile(
    r"([1-3]?[A-Z]{2,3}) "
    r"(\d+):(\d+)"
)

ROMANS_REMAP = {
    ("ROM", 14, 24): ("ROM", 16, 25),
    ("ROM", 14, 25): ("ROM", 16, 26),
    ("ROM", 14, 26): ("ROM", 16, 27),
}

EXPECTED_MISSING_CODES = {
    ("LUK", 17, 36),
    ("ACT", 8, 37),
    ("ACT", 15, 34),
}

DESCRIPTION = (
    "The New Testament, English Majority Text "
    "Version (EMTV). Copyright © 2014 "
    "Dr. Paul W. Esposito. Source: "
    "https://eBible.org/find/show.php?id=engemtv. "
    "Licensed under the Creative Commons "
    "Attribution-NonCommercial-NoDerivatives "
    "4.0 International License "
    "(CC BY-NC-ND 4.0): "
    "https://creativecommons.org/licenses/"
    "by-nc-nd/4.0/. This translation may be "
    "shared and redistributed with copyright "
    "and source information, must not be sold "
    "for profit, and its Scripture words and "
    "punctuation must not be changed. This "
    "database import preserves the Scripture "
    "words and punctuation. Notes, headings, "
    "cross-references, figures, sidebars, and "
    "other non-verse material are excluded. "
    "Reference mapping only: source Romans "
    "14:24-26 is stored at canonical Romans "
    "16:25-27, following the shared database "
    "versification. EMTV omits Luke 17:36, "
    "Acts 8:37, and Acts 15:34."
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
                        "Invalid verse marker "
                        f"{sid!r} in {path}"
                    )

                code, chapter, verse = (
                    match.groups()
                )

                active = (
                    code,
                    int(chapter),
                    int(verse),
                )

                if active in fragments:
                    raise CommandError(
                        "Duplicate verse marker "
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
        "English Majority Text Version",
        "<abbreviation>engEMTV</abbreviation>",
        "<iso>eng</iso>",
        "© 2014 Dr. Paul W. Esposito",
    ]

    for expected in required_metadata:
        if expected not in metadata:
            raise CommandError(
                "Expected metadata text was not "
                f"found: {expected!r}"
            )

    if 'id="55ec700d9e0d77ea"' not in (
        license_text
    ):
        raise CommandError(
            "Unexpected EMTV license identifier"
        )

    usx_paths = sorted(
        release_dir.rglob("*.usx")
    )

    if len(usx_paths) != 27:
        raise CommandError(
            "Expected 27 USX files, found "
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

    if len(raw_texts) != 7954:
        raise CommandError(
            "Expected 7,954 source texts, found "
            f"{len(raw_texts):,}"
        )

    return raw_texts


def normalize_positions(
    raw_texts,
    code_to_position,
):
    normalized = {}

    for source_reference, text in (
        raw_texts.items()
    ):
        if not text:
            code, chapter, verse = (
                source_reference
            )
            raise CommandError(
                "Blank source text at "
                f"{code} {chapter}:{verse}"
            )

        target_reference = ROMANS_REMAP.get(
            source_reference,
            source_reference,
        )

        code, chapter, verse = target_reference

        if code not in code_to_position:
            raise CommandError(
                f"Unsupported book code: {code}"
            )

        position = (
            code_to_position[code],
            chapter,
            verse,
        )

        if position in normalized:
            raise CommandError(
                "Duplicate normalized position: "
                f"{position}"
            )

        normalized[position] = text

    return normalized


class Command(BaseCommand):
    help = (
        "Import the English Majority Text "
        "Version New Testament from its "
        "DBL USX release bundle."
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
                "Source directory not found: "
                f"{source_dir}"
            )

        books = list(
            Book.objects.filter(
                position__gte=40,
                position__lte=66,
            ).order_by(
                "position"
            ).values_list(
                "position",
                "name",
            )
        )

        if len(books) != 27:
            raise CommandError(
                "Expected 27 canonical NT books, "
                f"found {len(books)}"
            )

        if len(BOOK_CODES) != 27:
            raise CommandError(
                "Internal NT book-code mapping "
                "is not complete"
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

        normalized = normalize_positions(
            raw_texts,
            code_to_position,
        )

        canonical_verses = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in Verse.objects.filter(
                chapter__book__position__gte=40,
                chapter__book__position__lte=66,
            ).select_related(
                "chapter__book"
            )
        }

        expected_missing = {
            (
                code_to_position[code],
                chapter,
                verse,
            )
            for code, chapter, verse
            in EXPECTED_MISSING_CODES
        }

        canonical_positions = set(
            canonical_verses
        )
        source_positions = set(normalized)

        missing = (
            canonical_positions
            - source_positions
        )
        extra = (
            source_positions
            - canonical_positions
        )

        if missing != expected_missing:
            raise CommandError(
                "Unexpected missing positions. "
                f"Expected: "
                f"{sorted(expected_missing)}; "
                f"found: {sorted(missing)}"
            )

        if extra:
            raise CommandError(
                "Unexpected extra positions: "
                f"{sorted(extra)}"
            )

        if len(normalized) != 7954:
            raise CommandError(
                "Expected 7,954 normalized verse "
                f"texts, found {len(normalized):,}"
            )

        forbidden_phrases = [
            "Copyright Information",
            "permission must be obtained",
            "DBLMetadata",
            "publicationRights",
            "English Majority Text Version",
            "Copyright ©",
        ]

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

            for phrase in forbidden_phrases:
                if phrase in text:
                    raise CommandError(
                        "Metadata contamination "
                        f"{phrase!r} at {position}"
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
                        "pdf_filename": "emtv.pdf",
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
            "Books: 27"
        )
        self.stdout.write(
            "Chapters: 260"
        )
        self.stdout.write(
            "Canonical NT positions: "
            f"{len(canonical_positions)}"
        )
        self.stdout.write(
            "Imported verse texts: "
            f"{len(normalized)}"
        )
        self.stdout.write(
            "Intentional/source missing "
            f"positions: {len(missing)}"
        )
        self.stdout.write(
            "Reference mapping: source Romans "
            "14:24-26 -> canonical Romans "
            "16:25-27"
        )
        self.stdout.write(
            "Scripture words and punctuation: "
            "unchanged"
        )
        self.stdout.write(
            "License: CC BY-NC-ND 4.0"
        )
        self.stdout.write(
            "Copyright: Copyright © 2014 "
            "Dr. Paul W. Esposito"
        )
        self.stdout.write(
            "PDF: emtv.pdf"
        )
