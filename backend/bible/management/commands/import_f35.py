import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Verse,
    VerseText,
)


BOOK_FILES = [
    ("MAT", "MT", "Matthew"),
    ("MRK", "MK", "Mark"),
    ("LUK", "LK", "Luke"),
    ("JHN", "JN", "John"),
    ("ACT", "AC", "Acts"),
    ("ROM", "RM", "Romans"),
    ("1CO", "C1", "1 Corinthians"),
    ("2CO", "C2", "2 Corinthians"),
    ("GAL", "GL", "Galatians"),
    ("EPH", "EP", "Ephesians"),
    ("PHP", "PP", "Philippians"),
    ("COL", "CL", "Colossians"),
    ("1TH", "H1", "1 Thessalonians"),
    ("2TH", "H2", "2 Thessalonians"),
    ("1TI", "T1", "1 Timothy"),
    ("2TI", "T2", "2 Timothy"),
    ("TIT", "TT", "Titus"),
    ("PHM", "PM", "Philemon"),
    ("HEB", "HB", "Hebrews"),
    ("JAS", "JM", "James"),
    ("1PE", "P1", "1 Peter"),
    ("2PE", "P2", "2 Peter"),
    ("1JN", "J1", "1 John"),
    ("2JN", "J2", "2 John"),
    ("3JN", "J3", "3 John"),
    ("JUD", "JD", "Jude"),
    ("REV", "RV", "Revelation"),
]

SKIP_CLASSES = {
    "tnav",
    "footnote",
    "f",
    "noteref",
    "notebackref",
    "notemark",
    "ft",
}

RESET_CLASSES = {
    "s",
    "s2",
    "s3",
    "s4",
    "ms",
    "ms2",
    "ms3",
    "mt",
    "mt2",
    "mt3",
    "psalmlabel",
}

EXPECTED_MISSING = {
    (42, 17, 36),
    (44, 8, 37),
    (44, 15, 34),
    (44, 24, 7),
}

ROMANS_REMAP = {
    (45, 14, 24): (45, 16, 25),
    (45, 14, 25): (45, 16, 26),
    (45, 14, 26): (45, 16, 27),
}

EXPECTED_BOOKS = 27
EXPECTED_CHAPTERS = 260
EXPECTED_CANONICAL_POSITIONS = 7957
EXPECTED_TEXTS = 7953
EXPECTED_NOTE_REFERENCES = 4718

EXPECTED_TITLE = (
    "The New Testament with Commentary"
)
EXPECTED_LANGUAGE = "en"
EXPECTED_RIGHTS = (
    "Copyright © 2016 Wilbur N. Pickering, "
    "ThM, PhD"
)

ATTRIBUTION = (
    "The New Testament with Commentary "
    "according to Family 35, 2nd Edition. "
    "Copyright © 2016 Wilbur N. Pickering, "
    "ThM, PhD. English Scripture text extracted "
    "without commentary from the licensed EPUB. "
    "Licensed under the Creative Commons "
    "Attribution-ShareAlike 4.0 International "
    "license (CC BY-SA 4.0)."
)

CONTAMINATION_PHRASES = {
    "There is no definite article",
    "The ‘wise men’",
    "Conception of Jesus",
    "The New Testament with Commentary",
    "copyright ©",
}


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def element_text(element):
    return re.sub(
        r"\s+",
        " ",
        "".join(element.itertext()),
    ).strip()


def normalize_text(value):
    text = re.sub(r"\s+", " ", value).strip()

    # Remove spacing introduced by inline formatting
    # elements immediately before punctuation.
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

    return text


def read_metadata(package):
    metadata = {}

    for element in package.iter():
        tag = local_name(element.tag)

        if tag not in {
            "title",
            "language",
            "rights",
        }:
            continue

        text = element_text(element)

        if text:
            metadata.setdefault(tag, []).append(text)

    return metadata


def extract_book(
    root,
    book_position,
    marker_prefix,
    book_name,
):
    extracted = {}
    raw_positions = set()
    current_key = None
    removed_notes = 0

    def append_text(value):
        if current_key is not None and value:
            extracted[current_key].append(value)

    def walk(element):
        nonlocal current_key
        nonlocal removed_notes

        tag = local_name(element.tag)
        classes = set(
            element.attrib.get(
                "class",
                "",
            ).split()
        )

        if tag == "aside":
            return

        if classes & RESET_CLASSES:
            current_key = None
            return

        if classes & SKIP_CLASSES:
            if "noteref" in classes:
                removed_notes += 1
            return

        if tag == "span" and "verse" in classes:
            marker_id = element.attrib.get("id", "")

            match = re.fullmatch(
                rf"{re.escape(marker_prefix)}"
                r"(\d+)_(\d+)",
                marker_id,
            )

            if not match:
                raise CommandError(
                    f"Malformed marker in {book_name}: "
                    f"{marker_id!r}"
                )

            raw_key = (
                book_position,
                int(match.group(1)),
                int(match.group(2)),
            )

            if raw_key in raw_positions:
                raise CommandError(
                    "Duplicate raw EPUB marker: "
                    f"{raw_key}"
                )

            raw_positions.add(raw_key)

            current_key = ROMANS_REMAP.get(
                raw_key,
                raw_key,
            )

            if current_key in extracted:
                raise CommandError(
                    "Duplicate extracted position: "
                    f"{current_key}"
                )

            extracted[current_key] = []
            return

        append_text(element.text)

        for child in element:
            walk(child)
            append_text(child.tail)

    walk(root)

    return (
        {
            key: normalize_text(" ".join(parts))
            for key, parts in extracted.items()
        },
        raw_positions,
        removed_notes,
    )


class Command(BaseCommand):
    help = (
        "Import the English Family 35 New "
        "Testament from its licensed EPUB."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            type=str,
            help="Path to f35.epub",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])

        if not source_path.is_file():
            raise CommandError(
                f"Source file not found: {source_path}"
            )

        if not zipfile.is_zipfile(source_path):
            raise CommandError(
                f"Source is not a valid EPUB ZIP: "
                f"{source_path}"
            )

        try:
            with zipfile.ZipFile(source_path) as archive:
                corrupt_file = archive.testzip()

                if corrupt_file is not None:
                    raise CommandError(
                        "Corrupt EPUB member: "
                        f"{corrupt_file}"
                    )

                required_files = {
                    "META-INF/container.xml",
                    "OEBPS/content.opf",
                    "OEBPS/copyright.xhtml",
                    *{
                        f"OEBPS/{filename}.xhtml"
                        for filename, _, _ in BOOK_FILES
                    },
                }

                missing_files = (
                    required_files
                    - set(archive.namelist())
                )

                if missing_files:
                    raise CommandError(
                        "Missing EPUB files: "
                        + ", ".join(
                            sorted(missing_files)
                        )
                    )

                package = ET.fromstring(
                    archive.read(
                        "OEBPS/content.opf"
                    )
                )
                metadata = read_metadata(package)

                if (
                    EXPECTED_TITLE
                    not in metadata.get("title", [])
                ):
                    raise CommandError(
                        "Unexpected EPUB title: "
                        f"{metadata.get('title')!r}"
                    )

                if (
                    EXPECTED_LANGUAGE
                    not in metadata.get(
                        "language",
                        [],
                    )
                ):
                    raise CommandError(
                        "Unexpected EPUB language: "
                        f"{metadata.get('language')!r}"
                    )

                if (
                    EXPECTED_RIGHTS
                    not in metadata.get("rights", [])
                ):
                    raise CommandError(
                        "Unexpected EPUB rights: "
                        f"{metadata.get('rights')!r}"
                    )

                copyright_root = ET.fromstring(
                    archive.read(
                        "OEBPS/copyright.xhtml"
                    )
                )
                copyright_text = element_text(
                    copyright_root
                )

                required_license_phrases = {
                    (
                        "The New Testament with "
                        "Commentary according to "
                        "Family 35, 2nd Edition"
                    ),
                    (
                        "Creative Commons Attribution "
                        "Share-Alike license 4.0"
                    ),
                    (
                        "permission to share and "
                        "redistribute this Bible "
                        "translation"
                    ),
                    (
                        "include the above copyright "
                        "and source information"
                    ),
                    (
                        "distribute your contributions "
                        "under the same license"
                    ),
                }

                absent_license_phrases = {
                    phrase
                    for phrase in (
                        required_license_phrases
                    )
                    if phrase not in copyright_text
                }

                if absent_license_phrases:
                    raise CommandError(
                        "Required licence wording is "
                        "missing: "
                        + "; ".join(
                            sorted(
                                absent_license_phrases
                            )
                        )
                    )

                source = {}
                raw_positions = set()
                removed_notes = 0
                source_chapters = set()

                for book_position, (
                    filename_code,
                    marker_prefix,
                    book_name,
                ) in enumerate(
                    BOOK_FILES,
                    start=40,
                ):
                    root = ET.fromstring(
                        archive.read(
                            "OEBPS/"
                            f"{filename_code}.xhtml"
                        )
                    )

                    (
                        book_source,
                        book_raw_positions,
                        book_removed_notes,
                    ) = extract_book(
                        root,
                        book_position,
                        marker_prefix,
                        book_name,
                    )

                    overlap = (
                        set(source)
                        & set(book_source)
                    )

                    if overlap:
                        raise CommandError(
                            "Duplicate canonical "
                            "positions: "
                            f"{sorted(overlap)[:20]}"
                        )

                    source.update(book_source)
                    raw_positions.update(
                        book_raw_positions
                    )
                    removed_notes += (
                        book_removed_notes
                    )

                    source_chapters.update(
                        (
                            key[0],
                            key[1],
                        )
                        for key in book_source
                    )

        except (
            OSError,
            zipfile.BadZipFile,
            ET.ParseError,
        ) as error:
            raise CommandError(
                f"Unable to read EPUB: {error}"
            ) from error

        if len(raw_positions) != EXPECTED_TEXTS:
            raise CommandError(
                f"Expected {EXPECTED_TEXTS} raw verse "
                f"markers, found {len(raw_positions)}"
            )

        if len(source) != EXPECTED_TEXTS:
            raise CommandError(
                f"Expected {EXPECTED_TEXTS} extracted "
                f"texts, found {len(source)}"
            )

        if len(source_chapters) != EXPECTED_CHAPTERS:
            raise CommandError(
                f"Expected {EXPECTED_CHAPTERS} "
                f"chapters, found "
                f"{len(source_chapters)}"
            )

        if (
            removed_notes
            != EXPECTED_NOTE_REFERENCES
        ):
            raise CommandError(
                f"Expected to remove "
                f"{EXPECTED_NOTE_REFERENCES} note "
                f"references, removed {removed_notes}"
            )

        blank_positions = {
            key
            for key, text in source.items()
            if not text
        }

        if blank_positions:
            raise CommandError(
                "Blank extracted texts: "
                f"{sorted(blank_positions)[:20]}"
            )

        replacement_positions = {
            key
            for key, text in source.items()
            if "\ufffd" in text
        }

        if replacement_positions:
            raise CommandError(
                "Replacement characters at: "
                f"{sorted(replacement_positions)[:20]}"
            )

        html_positions = {
            key
            for key, text in source.items()
            if re.search(r"<[^>]+>", text)
        }

        if html_positions:
            raise CommandError(
                "HTML markers at: "
                f"{sorted(html_positions)[:20]}"
            )

        for phrase in CONTAMINATION_PHRASES:
            contaminated = {
                key
                for key, text in source.items()
                if phrase in text
            }

            if contaminated:
                raise CommandError(
                    f"Commentary contamination "
                    f"{phrase!r} at "
                    f"{sorted(contaminated)[:20]}"
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
                "chapter__book",
            )
        }

        if (
            len(canonical_verses)
            != EXPECTED_CANONICAL_POSITIONS
        ):
            raise CommandError(
                f"Expected "
                f"{EXPECTED_CANONICAL_POSITIONS} "
                "canonical NT positions, found "
                f"{len(canonical_verses)}"
            )

        missing = (
            set(canonical_verses) - set(source)
        )
        extra = (
            set(source) - set(canonical_verses)
        )

        if missing != EXPECTED_MISSING or extra:
            raise CommandError(
                "Canonical validation failed. "
                f"Missing: {sorted(missing)}; "
                f"extra: {sorted(extra)}"
            )

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation="F35",
                    defaults={
                        "name": (
                            "Family 35 New Testament"
                        ),
                        "language": "English",
                        "year": 2016,
                    },
                )
            )

            version.name = (
                "Family 35 New Testament"
            )
            version.language = "English"
            version.year = 2016
            version.description = ATTRIBUTION
            version.pdf_filename = "f35.pdf"
            version.save()

            # This replacement is atomic. If inserting
            # the English texts fails, the previous
            # F35 texts are restored automatically.
            VerseText.objects.filter(
                bible_version=version
            ).delete()

            verse_texts = [
                VerseText(
                    bible_version=version,
                    verse=canonical_verses[key],
                    text=text,
                )
                for key, text in source.items()
            ]

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=1000,
            )

        action = "Created" if created else "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.name} "
                f"({version.abbreviation})"
            )
        )
        self.stdout.write("Language: English")
        self.stdout.write("Year: 2016")
        self.stdout.write(
            f"Books: {EXPECTED_BOOKS}"
        )
        self.stdout.write(
            f"Chapters: {len(source_chapters)}"
        )
        self.stdout.write(
            f"Imported verse texts: "
            f"{len(verse_texts)}"
        )
        self.stdout.write(
            f"Intentional missing positions: "
            f"{len(missing)}"
        )
        self.stdout.write(
            "Romans 14:24-26 remapped to "
            "Romans 16:25-27"
        )
        self.stdout.write(
            f"Commentary note references removed: "
            f"{removed_notes}"
        )
        self.stdout.write(
            "License: CC BY-SA 4.0"
        )
        self.stdout.write("PDF: f35.pdf")
