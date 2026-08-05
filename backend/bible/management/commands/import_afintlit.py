import hashlib
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from bible.models import (
    BibleVersion,
    Chapter,
    Verse,
    VerseText,
)


VERSION_NAME = (
    "African International New Testament: "
    "Literal Translation"
)
ABBREVIATION = "AFINTLIT"
LANGUAGE = "English"
YEAR = 2026
PDF_FILENAME = ""

SOURCE_FOLDER = (
    "African International New Testament: "
    "Literal Translation"
)

BUNDLE_ID = "e368831dd78a4451"
EXPECTED_METADATA_VERSION = "2.2.1"
EXPECTED_SCOPE = "New Testament"
EXPECTED_LANGUAGE_CODE = "eng"
EXPECTED_LICENSE_DATE = "2026-02-27"

COPYRIGHT_STATEMENT = (
    "Copyright © 2026 Michael Adeyemi Adegbola."
)

LICENSE_NAME = "CC BY-SA 4.0"
LICENSE_URL = (
    "https://creativecommons.org/licenses/"
    "by-sa/4.0/"
)
RIGHTS_HOLDER_URL = (
    "https://www.wordbiblicalministries.org"
)

DESCRIPTION = (
    "African International New Testament: "
    "Literal Translation (American English "
    "Edition). Copyright © 2026 Michael Adeyemi "
    "Adegbola. Rights holder: Word Biblical "
    "Ministries. Licensed under the Creative "
    "Commons Attribution-ShareAlike 4.0 "
    "International License (CC BY-SA 4.0): "
    f"{LICENSE_URL} Source: {RIGHTS_HOLDER_URL} "
    "USX verse markers were normalized for this "
    "application: embedded Mark 2:14 and "
    "Galatians 5:14 were separated from their "
    "preceding verses; unmarked Luke 9:37, "
    "Acts 4:25-26, and Colossians 4:18 text was "
    "recovered; a duplicate Luke 22:1 "
    "cross-reference was excluded; 3 John 1:15 "
    "was combined with canonical 3 John 1:14; "
    "and Revelation 12:18 was combined with "
    "canonical Revelation 13:1."
)

BOOK_CODES = {
    "MAT": (40, "Matthew"),
    "MRK": (41, "Mark"),
    "LUK": (42, "Luke"),
    "JHN": (43, "John"),
    "ACT": (44, "Acts"),
    "ROM": (45, "Romans"),
    "1CO": (46, "1 Corinthians"),
    "2CO": (47, "2 Corinthians"),
    "GAL": (48, "Galatians"),
    "EPH": (49, "Ephesians"),
    "PHP": (50, "Philippians"),
    "COL": (51, "Colossians"),
    "1TH": (52, "1 Thessalonians"),
    "2TH": (53, "2 Thessalonians"),
    "1TI": (54, "1 Timothy"),
    "2TI": (55, "2 Timothy"),
    "TIT": (56, "Titus"),
    "PHM": (57, "Philemon"),
    "HEB": (58, "Hebrews"),
    "JAS": (59, "James"),
    "1PE": (60, "1 Peter"),
    "2PE": (61, "2 Peter"),
    "1JN": (62, "1 John"),
    "2JN": (63, "2 John"),
    "3JN": (64, "3 John"),
    "JUD": (65, "Jude"),
    "REV": (66, "Revelation"),
}

EXPECTED_MISSING = {
    (40, 17, 21),
    (40, 18, 11),
    (40, 23, 14),
    (41, 7, 16),
    (41, 9, 44),
    (41, 9, 46),
    (41, 11, 26),
    (41, 15, 28),
    (42, 17, 36),
    (42, 23, 17),
    (43, 5, 4),
    (44, 8, 37),
    (44, 15, 34),
    (44, 24, 7),
    (44, 28, 29),
    (45, 16, 24),
}

EXCLUDED_TAGS = {
    "note",
    "figure",
    "sidebar",
}


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def normalize_text(parts):
    text = re.sub(
        r"\s+",
        " ",
        "".join(parts),
    )
    text = re.sub(
        r"\s+([,.;:!?])",
        r"\1",
        text,
    )
    return text.strip()


def leaf_text(element):
    return normalize_text(
        list(element.itertext())
    )


class Command(BaseCommand):
    help = (
        "Import the African International New "
        "Testament Literal Translation from its "
        "DBL USX bundle."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source_dir",
            nargs="?",
            default=str(
                Path("data") / SOURCE_FOLDER
            ),
            help=(
                "Directory containing metadata.xml, "
                "license.xml, and the release folder."
            ),
        )

    def handle(self, *args, **options):
        source_dir = Path(
            options["source_dir"]
        ).expanduser()

        if not source_dir.is_dir():
            raise CommandError(
                f"Source directory not found: "
                f"{source_dir}"
            )

        metadata_path = (
            source_dir / "metadata.xml"
        )
        license_path = (
            source_dir / "license.xml"
        )

        for path in [
            metadata_path,
            license_path,
        ]:
            if not path.is_file():
                raise CommandError(
                    f"Required file not found: {path}"
                )

        try:
            metadata_root = ET.parse(
                metadata_path
            ).getroot()
            license_root = ET.parse(
                license_path
            ).getroot()
        except ET.ParseError as error:
            raise CommandError(
                f"Invalid XML: {error}"
            ) from error

        self.validate_metadata(
            metadata_root,
        )
        self.validate_license(
            license_root,
        )

        resources = self.load_resources(
            source_dir,
            metadata_root,
        )

        self.validate_manifest(
            source_dir,
            metadata_root,
        )

        occurrences = self.extract_occurrences(
            resources,
        )
        source_texts, adjustments = (
            self.normalize_versification(
                occurrences,
                resources,
            )
        )

        canonical_verses = {
            (
                verse.chapter.book.position,
                verse.chapter.number,
                verse.number,
            ): verse
            for verse in (
                Verse.objects
                .select_related(
                    "chapter__book"
                )
                .filter(
                    chapter__book__position__gte=40,
                    chapter__book__position__lte=66,
                )
            )
        }

        canonical_positions = set(
            canonical_verses
        )
        source_positions = set(source_texts)

        missing = (
            canonical_positions
            - source_positions
        )
        extra = (
            source_positions
            - canonical_positions
        )

        if len(canonical_positions) != 7957:
            raise CommandError(
                "Expected 7,957 canonical NT "
                "positions, found "
                f"{len(canonical_positions)}."
            )

        if missing != EXPECTED_MISSING:
            raise CommandError(
                "Unexpected missing positions.\n"
                f"Expected: "
                f"{sorted(EXPECTED_MISSING)}\n"
                f"Found: {sorted(missing)}"
            )

        if extra:
            raise CommandError(
                "Unexpected extra positions: "
                f"{sorted(extra)}"
            )

        if len(source_texts) != 7941:
            raise CommandError(
                "Expected 7,941 normalized verse "
                f"texts, found {len(source_texts)}."
            )

        self.validate_texts(
            source_texts,
        )

        verse_text_objects = [
            VerseText(
                bible_version=None,
                verse=canonical_verses[key],
                text=text,
            )
            for key, text in sorted(
                source_texts.items()
            )
        ]

        with transaction.atomic():
            version, created = (
                BibleVersion.objects.get_or_create(
                    abbreviation=ABBREVIATION,
                    defaults={
                        "name": VERSION_NAME,
                        "language": LANGUAGE,
                        "year": YEAR,
                        "description": DESCRIPTION,
                        "pdf_filename": PDF_FILENAME,
                    },
                )
            )

            version.name = VERSION_NAME
            version.language = LANGUAGE
            version.year = YEAR
            version.description = DESCRIPTION
            version.pdf_filename = PDF_FILENAME
            version.save()

            VerseText.objects.filter(
                bible_version=version
            ).delete()

            for item in verse_text_objects:
                item.bible_version = version

            VerseText.objects.bulk_create(
                verse_text_objects,
                batch_size=1000,
            )

        action = (
            "Created"
            if created
            else "Updated"
        )

        chapter_count = (
            Chapter.objects.filter(
                book__position__gte=40,
                book__position__lte=66,
            )
            .values(
                "book_id",
                "number",
            )
            .distinct()
            .count()
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
            f"Books: {len(resources)}"
        )
        self.stdout.write(
            f"Chapters: {chapter_count}"
        )
        self.stdout.write(
            "Canonical NT positions: "
            f"{len(canonical_positions)}"
        )
        self.stdout.write(
            "Imported verse texts: "
            f"{len(verse_text_objects)}"
        )
        self.stdout.write(
            "Intentional/source missing "
            f"positions: {len(missing)}"
        )

        for adjustment in adjustments:
            self.stdout.write(
                f"Normalization: {adjustment}"
            )

        self.stdout.write(
            f"License: {LICENSE_NAME}"
        )
        self.stdout.write(
            "Copyright: "
            f"{COPYRIGHT_STATEMENT}"
        )
        self.stdout.write(
            "PDF: not configured"
        )

    def validate_metadata(
        self,
        root,
    ):
        if local_name(root.tag) != "DBLMetadata":
            raise CommandError(
                "metadata.xml is not DBLMetadata."
            )

        if root.get("id") != BUNDLE_ID:
            raise CommandError(
                "Unexpected metadata bundle ID."
            )

        if (
            root.get("version")
            != EXPECTED_METADATA_VERSION
        ):
            raise CommandError(
                "Unexpected DBL metadata version."
            )

        identification = root.find(
            "identification"
        )
        language = root.find("language")
        content_type = root.find("type")
        copyright_element = root.find(
            "copyright/fullStatement/"
            "statementContent"
        )

        if identification is None:
            raise CommandError(
                "Missing identification metadata."
            )

        expected_identification = {
            "name": (
                "African International New "
                "Testament: Literal Translation "
                "(American English Edition)"
            ),
            "abbreviation": ABBREVIATION,
            "scope": EXPECTED_SCOPE,
        }

        for tag, expected in (
            expected_identification.items()
        ):
            actual = identification.findtext(tag)

            if actual != expected:
                raise CommandError(
                    f"Unexpected {tag}: "
                    f"{actual!r}"
                )

        if (
            language is None
            or language.findtext("iso")
            != EXPECTED_LANGUAGE_CODE
        ):
            raise CommandError(
                "Unexpected source language."
            )

        if (
            content_type is None
            or content_type.findtext(
                "isConfidential"
            )
            != "false"
        ):
            raise CommandError(
                "Source is marked confidential "
                "or lacks its confidentiality flag."
            )

        rights_holder = root.find(
            "agencies/rightsHolder"
        )

        if (
            rights_holder is None
            or leaf_text(
                rights_holder.find("name")
            )
            != "Word Biblical Ministries"
        ):
            raise CommandError(
                "Unexpected rights holder."
            )

        if (
            rights_holder.findtext("url")
            != RIGHTS_HOLDER_URL
        ):
            raise CommandError(
                "Unexpected rights-holder URL."
            )

        if copyright_element is None:
            raise CommandError(
                "Missing copyright statement."
            )

        copyright_text = leaf_text(
            copyright_element
        )

        if (
            COPYRIGHT_STATEMENT
            not in copyright_text
            or LICENSE_NAME
            not in copyright_text
        ):
            raise CommandError(
                "Required copyright/license "
                "statement was not found."
            )

        publication = root.find(
            ".//publication[@default='true']"
        )

        if publication is None:
            raise CommandError(
                "Default publication not found."
            )

        if (
            publication.findtext(
                "abbreviation"
            )
            != ABBREVIATION
        ):
            raise CommandError(
                "Unexpected publication "
                "abbreviation."
            )

    def validate_license(
        self,
        root,
    ):
        if local_name(root.tag) != "license":
            raise CommandError(
                "license.xml has an unexpected "
                "root element."
            )

        if root.get("id") != BUNDLE_ID:
            raise CommandError(
                "License and metadata bundle IDs "
                "do not match."
            )

        if (
            root.findtext("dateLicense")
            != EXPECTED_LICENSE_DATE
        ):
            raise CommandError(
                "Unexpected license date."
            )

        expected_rights = {
            "allowIntroductions": "True",
            "allowFootnotes": "True",
            "allowCrossReferences": "True",
            "allowExtendedNotes": "True",
        }

        rights = root.find(
            "publicationRights"
        )

        if rights is None:
            raise CommandError(
                "Publication rights are missing."
            )

        for tag, expected in (
            expected_rights.items()
        ):
            if rights.findtext(tag) != expected:
                raise CommandError(
                    f"Publication right {tag} "
                    "is not enabled."
                )

    def load_resources(
        self,
        source_dir,
        metadata_root,
    ):
        resources = {}

        divisions = metadata_root.findall(
            ".//publication[@default='true']"
            "/structure/division"
        )

        for division in divisions:
            role = division.get("role")
            content = division.find("content")

            if role not in BOOK_CODES:
                raise CommandError(
                    "Unexpected book role: "
                    f"{role!r}"
                )

            if (
                content is None
                or not content.get("src")
            ):
                raise CommandError(
                    f"Missing source path for {role}."
                )

            path = (
                source_dir
                / content.get("src")
            )

            if not path.is_file():
                raise CommandError(
                    f"USX file not found: {path}"
                )

            if role in resources:
                raise CommandError(
                    f"Duplicate book role: {role}"
                )

            resources[role] = path

        if set(resources) != set(BOOK_CODES):
            missing = (
                set(BOOK_CODES)
                - set(resources)
            )
            raise CommandError(
                "Bundle does not contain exactly "
                "the 27 NT books. Missing roles: "
                f"{sorted(missing)}"
            )

        return resources

    def validate_manifest(
        self,
        source_dir,
        metadata_root,
    ):
        manifest_resources = (
            metadata_root.findall(
                "manifest/resource"
            )
        )

        if len(manifest_resources) != 27:
            raise CommandError(
                "Expected 27 manifest resources, "
                f"found {len(manifest_resources)}."
            )

        seen_paths = set()

        for resource in manifest_resources:
            uri = resource.get("uri")
            checksum = resource.get("checksum")
            size = resource.get("size")
            mime_type = resource.get(
                "mimeType"
            )

            if (
                not uri
                or not checksum
                or not size
            ):
                raise CommandError(
                    "Incomplete manifest resource."
                )

            if mime_type != "application/xml":
                raise CommandError(
                    "Unexpected resource MIME type "
                    f"for {uri}: {mime_type!r}"
                )

            path = source_dir / uri

            if not path.is_file():
                raise CommandError(
                    f"Manifest file not found: {path}"
                )

            if path.stat().st_size != int(size):
                raise CommandError(
                    f"Size mismatch for {path}"
                )

            digest = hashlib.md5(
                path.read_bytes()
            ).hexdigest()

            if digest.lower() != checksum.lower():
                raise CommandError(
                    f"Checksum mismatch for {path}"
                )

            if uri in seen_paths:
                raise CommandError(
                    "Duplicate manifest URI: "
                    f"{uri}"
                )

            seen_paths.add(uri)

    def extract_occurrences(
        self,
        resources,
    ):
        occurrences = defaultdict(list)

        for role, path in resources.items():
            position, _ = BOOK_CODES[role]

            try:
                root = ET.parse(path).getroot()
            except ET.ParseError as error:
                raise CommandError(
                    f"Invalid USX in {path}: "
                    f"{error}"
                ) from error

            book_elements = [
                element
                for element in root.iter()
                if local_name(element.tag)
                == "book"
            ]

            if len(book_elements) != 1:
                raise CommandError(
                    f"Expected one book element "
                    f"in {path}."
                )

            if (
                book_elements[0].get("code")
                != role
            ):
                raise CommandError(
                    f"Book-code mismatch in {path}."
                )

            state = {
                "key": None,
                "parts": [],
            }

            def finish():
                key = state["key"]

                if key is not None:
                    text = normalize_text(
                        state["parts"]
                    )
                    occurrences[key].append(
                        text
                    )

                state["key"] = None
                state["parts"] = []

            def append(value):
                if (
                    state["key"] is not None
                    and value
                ):
                    state["parts"].append(value)

            def walk(element):
                tag = local_name(element.tag)

                if tag == "verse":
                    sid = element.get("sid")
                    eid = element.get("eid")

                    if sid:
                        if state["key"] is not None:
                            raise CommandError(
                                "Encountered a new "
                                "verse before closing "
                                f"{state['key']} in "
                                f"{path}."
                            )

                        match = re.fullmatch(
                            rf"{re.escape(role)} "
                            r"(\d+):(\d+)",
                            sid,
                        )

                        if not match:
                            raise CommandError(
                                "Invalid verse marker "
                                f"{sid!r} in {path}."
                            )

                        state["key"] = (
                            position,
                            int(match.group(1)),
                            int(match.group(2)),
                        )
                        state["parts"] = []

                    elif eid:
                        if state["key"] is None:
                            raise CommandError(
                                "Closing verse without "
                                f"an open verse in {path}."
                            )

                        expected = (
                            f"{role} "
                            f"{state['key'][1]}:"
                            f"{state['key'][2]}"
                        )

                        if eid != expected:
                            raise CommandError(
                                "Mismatched closing "
                                f"marker {eid!r}; "
                                f"expected {expected!r}."
                            )

                        finish()

                    else:
                        raise CommandError(
                            "Verse element lacks both "
                            f"sid and eid in {path}."
                        )

                    return

                if tag in EXCLUDED_TAGS:
                    return

                append(element.text)

                for child in element:
                    walk(child)
                    append(child.tail)

            walk(root)

            if state["key"] is not None:
                raise CommandError(
                    "Unclosed final verse in "
                    f"{path}: {state['key']}"
                )

        return occurrences

    def normalize_versification(
        self,
        occurrences,
        resources,
    ):
        texts = {}
        adjustments = []

        for key, values in occurrences.items():
            if key == (42, 22, 1):
                expected_values = [
                    (
                        "Now the Feast of Unleavened "
                        "Bread, which is called the "
                        "Passover, was drawing near."
                    ),
                    "Cor. 11:23-25",
                ]

                if values != expected_values:
                    raise CommandError(
                        "Unexpected duplicate "
                        "Luke 22:1 content."
                    )

                texts[key] = values[0]
                adjustments.append(
                    "discarded duplicate Luke 22:1 "
                    "cross-reference"
                )
                continue

            if len(values) != 1:
                raise CommandError(
                    "Unexpected duplicate position "
                    f"{key}: {len(values)} texts."
                )

            texts[key] = values[0]

        def normalized_document(role):
            try:
                value = resources[
                    role
                ].read_text(
                    encoding="utf-8-sig",
                )
            except OSError as error:
                raise CommandError(
                    f"Could not read {role} source: "
                    f"{error}"
                ) from error

            return re.sub(
                r"\s+",
                " ",
                value,
            )

        mark_combined = texts[(41, 2, 13)]
        mark_delimiter = (
            " 4 And as He passed by,"
        )

        if mark_delimiter not in mark_combined:
            raise CommandError(
                "Embedded Mark 2:14 delimiter "
                "was not found."
            )

        mark_13, mark_14 = (
            mark_combined.split(
                mark_delimiter,
                1,
            )
        )

        texts[(41, 2, 13)] = (
            normalize_text([mark_13])
        )
        texts[(41, 2, 14)] = (
            normalize_text(
                [
                    "And as He passed by,",
                    mark_14,
                ]
            )
        )

        adjustments.append(
            "split embedded Mark 2:14 "
            "from Mark 2:13"
        )

        luke_37 = (
            "Now on the next day, it occurred that "
            "when they had come down from the "
            "mountain, a large crowd met Him."
        )

        if (
            luke_37
            not in normalized_document("LUK")
        ):
            raise CommandError(
                "Unmarked Luke 9:37 text "
                "was not found."
            )

        texts[(42, 9, 37)] = luke_37

        adjustments.append(
            "recovered unmarked Luke 9:37"
        )

        acts_25_lines = [
            "‘Why did the nations rage,",
            (
                "and the peoples devise vain "
                "things?"
            ),
        ]

        acts_26_lines = [
            (
                "26The kings of the earth took "
                "their stand,"
            ),
            (
                "and the rulers gathered "
                "themselves together,"
            ),
            (
                "against the Lord and against "
                "His Anointed One.’*"
            ),
        ]

        acts_document = normalized_document(
            "ACT"
        )

        for fragment in (
            acts_25_lines + acts_26_lines
        ):
            if fragment not in acts_document:
                raise CommandError(
                    "Required Acts recovery "
                    f"fragment not found: "
                    f"{fragment!r}"
                )

        texts[(44, 4, 25)] = (
            normalize_text(
                [
                    texts[(44, 4, 25)],
                    " ",
                    " ".join(
                        acts_25_lines
                    ),
                ]
            )
        )

        texts[(44, 4, 26)] = (
            normalize_text(
                [
                    re.sub(
                        r"^26",
                        "",
                        acts_26_lines[0],
                    ),
                    " ",
                    " ".join(
                        acts_26_lines[1:]
                    ),
                ]
            )
        )

        adjustments.append(
            "recovered unmarked Acts 4:25 "
            "quotation continuation"
        )
        adjustments.append(
            "recovered unmarked Acts 4:26"
        )

        galatians_combined = texts[
            (48, 5, 13)
        ]
        galatians_delimiter = (
            " 4 For the entire Law"
        )

        if (
            galatians_delimiter
            not in galatians_combined
        ):
            raise CommandError(
                "Embedded Galatians 5:14 "
                "delimiter was not found."
            )

        (
            galatians_13,
            galatians_14_tail,
        ) = galatians_combined.split(
            galatians_delimiter,
            1,
        )

        texts[(48, 5, 13)] = (
            normalize_text(
                [galatians_13]
            )
        )
        texts[(48, 5, 14)] = (
            normalize_text(
                [
                    "For the entire Law",
                    galatians_14_tail,
                ]
            )
        )

        adjustments.append(
            "split embedded Galatians 5:14 "
            "from Galatians 5:13"
        )

        colossians_raw = (
            "18. I, Paul, write this greeting in "
            "my own hand.* Remember my "
            "imprisonment. Grace be with you.*"
        )

        if (
            colossians_raw
            not in normalized_document("COL")
        ):
            raise CommandError(
                "Unmarked Colossians 4:18 "
                "text was not found."
            )

        texts[(51, 4, 18)] = re.sub(
            r"^18\.\s*",
            "",
            colossians_raw,
        )

        adjustments.append(
            "recovered unmarked "
            "Colossians 4:18"
        )

        third_john_15 = texts.pop(
            (64, 1, 15),
            None,
        )

        if not third_john_15:
            raise CommandError(
                "3 John 1:15 was not found."
            )

        texts[(64, 1, 14)] = (
            normalize_text(
                [
                    texts[(64, 1, 14)],
                    " ",
                    third_john_15,
                ]
            )
        )

        adjustments.append(
            "combined 3 John 1:15 with "
            "canonical 3 John 1:14"
        )

        revelation_12_18 = texts.pop(
            (66, 12, 18),
            None,
        )

        if not revelation_12_18:
            raise CommandError(
                "Revelation 12:18 "
                "was not found."
            )

        texts[(66, 13, 1)] = (
            normalize_text(
                [
                    revelation_12_18,
                    " ",
                    texts[(66, 13, 1)],
                ]
            )
        )

        adjustments.append(
            "combined Revelation 12:18 "
            "with canonical Revelation 13:1"
        )

        return texts, adjustments

    def validate_texts(
        self,
        source_texts,
    ):
        blank = [
            key
            for key, text
            in source_texts.items()
            if not text
        ]
        replacement = [
            key
            for key, text
            in source_texts.items()
            if "\ufffd" in text
        ]
        html = [
            key
            for key, text
            in source_texts.items()
            if re.search(r"<[^>]+>", text)
        ]

        if blank:
            raise CommandError(
                f"Blank verse texts: {blank}"
            )

        if replacement:
            raise CommandError(
                "Replacement characters found at: "
                f"{replacement}"
            )

        if html:
            raise CommandError(
                "HTML/XML markers found at: "
                f"{html}"
            )
