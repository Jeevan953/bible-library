import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import HitchcockName


EXPECTED_SOURCE_SHA256 = (
    "ad1182b7cdeec38260c9c750d6c02247"
    "e9295d46f2217ef54d841e9c2825d1a8"
)
EXPECTED_CANONICAL_SHA256 = (
    "2ec4afd0adc95eb0a41ac265debb3a6d"
    "6a0815f92f4a8279145df24d666cebda"
)
EXPECTED_ENTRY_COUNT = 2623
EXPECTED_DUPLICATE_NAME_GROUPS = 4


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_text(element):
    return re.sub(
        r"\s+",
        " ",
        " ".join(element.itertext()),
    ).strip()


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def metadata_values(root, requested_tag):
    return [
        clean_text(element)
        for element in root.iter()
        if local_name(element.tag) == requested_tag
    ]


def parse_entries(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise CommandError(f"Invalid Hitchcock XML: {error}") from error

    rights = metadata_values(root, "DC.Rights")

    if rights != ["Public Domain"]:
        raise CommandError(
            "Expected one Public Domain rights statement; "
            f"found {rights!r}."
        )

    records = []
    seen_ids = set()
    structure_errors = []

    glossaries = [
        element
        for element in root.iter()
        if local_name(element.tag) == "glossary"
    ]

    for glossary_number, glossary in enumerate(
        glossaries,
        start=1,
    ):
        children = [
            element
            for element in glossary
            if local_name(element.tag) in {"term", "def"}
        ]

        if len(children) % 2:
            structure_errors.append(
                f"Glossary {glossary_number} has an odd child count."
            )

        for index in range(0, len(children), 2):
            pair = children[index:index + 2]

            if len(pair) != 2:
                continue

            term_element, definition_element = pair

            if (
                local_name(term_element.tag),
                local_name(definition_element.tag),
            ) != ("term", "def"):
                structure_errors.append(
                    f"Glossary {glossary_number}, pair "
                    f"{index // 2 + 1} is not term/def."
                )
                continue

            source_id = term_element.get("id", "").strip()
            name = clean_text(term_element)
            definition = clean_text(definition_element)

            if not source_id or not name or not definition:
                raise CommandError(
                    "A Hitchcock record contains a blank ID, "
                    "name, or definition."
                )

            if source_id in seen_ids:
                raise CommandError(
                    f"Duplicate Hitchcock source ID: {source_id}"
                )

            if len(source_id) > 64 or len(name) > 200:
                raise CommandError(
                    f"Hitchcock record exceeds model limits: {source_id}"
                )

            seen_ids.add(source_id)
            records.append(
                {
                    "source_id": source_id,
                    "name": name,
                    "definition": definition,
                }
            )

    if structure_errors:
        raise CommandError("\n".join(structure_errors[:30]))

    return glossaries, records


class Command(BaseCommand):
    help = "Import Hitchcock's public-domain Bible names XML."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Path to Hitchcock's Bible Names ThML XML file.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the source without changing the database.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        source_sha256 = sha256_file(path)

        if source_sha256 != EXPECTED_SOURCE_SHA256:
            raise CommandError(
                "Hitchcock source checksum differs: "
                f"{source_sha256}"
            )

        glossaries, records = parse_entries(path)

        canonical = "\n".join(
            f"{record['source_id']}\t"
            f"{record['name']}\t"
            f"{record['definition']}"
            for record in records
        )
        canonical_sha256 = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

        duplicate_groups = sum(
            1
            for count in Counter(
                record["name"].casefold()
                for record in records
            ).values()
            if count > 1
        )

        if len(records) != EXPECTED_ENTRY_COUNT:
            raise CommandError(
                f"Expected {EXPECTED_ENTRY_COUNT} entries; "
                f"found {len(records)}."
            )

        if duplicate_groups != EXPECTED_DUPLICATE_NAME_GROUPS:
            raise CommandError(
                "Expected four duplicate-name groups; "
                f"found {duplicate_groups}."
            )

        if canonical_sha256 != EXPECTED_CANONICAL_SHA256:
            raise CommandError(
                "Hitchcock canonical checksum differs: "
                f"{canonical_sha256}"
            )

        self.stdout.write("HITCHCOCK IMPORT VALIDATION")
        self.stdout.write(f"Source: {path.resolve()}")
        self.stdout.write(f"Glossaries: {len(glossaries)}")
        self.stdout.write(f"Entries: {len(records)}")
        self.stdout.write(
            f"Duplicate-name groups preserved: {duplicate_groups}"
        )
        self.stdout.write(
            f"Canonical SHA256: {canonical_sha256}"
        )
        self.stdout.write("Rights: Public Domain")
        self.stdout.write("Author: Roswell D. Hitchcock")
        self.stdout.write(
            "Electronic source: Christian Classics Ethereal Library"
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run passed. No database records were changed."
                )
            )
            return

        objects = [
            HitchcockName(
                source_id=record["source_id"],
                name=record["name"],
                definition=record["definition"],
            )
            for record in records
        ]

        with transaction.atomic():
            HitchcockName.objects.all().delete()
            HitchcockName.objects.bulk_create(
                objects,
                batch_size=1000,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Hitchcock Bible names imported successfully."
            )
        )
