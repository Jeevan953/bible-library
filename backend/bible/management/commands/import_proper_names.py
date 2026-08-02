import html
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.html import strip_tags

from bible.models import ProperName


CATEGORY_MAP = {
    "PERSON": ProperName.Category.PERSON,
    "PLACE": ProperName.Category.PLACE,
    "OTHER": ProperName.Category.OTHER,
}


def clean_text(value):
    value = html.unescape(strip_tags(value or ""))
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def split_columns(line):
    columns = [column.strip() for column in line.split("\t")]

    while columns and not columns[-1]:
        columns.pop()

    return columns


def parse_references(value):
    references = []

    for reference in (value or "").split(";"):
        reference = reference.strip()

        if reference and reference not in references:
            references.append(reference)

    return references


def parse_descriptions(lines):
    descriptions = {
        "briefest": "",
        "brief": "",
        "short_description": "",
        "article": "",
    }

    marker_map = {
        "@Briefest=": "briefest",
        "@Brief=": "brief",
        "@Short=": "short_description",
        "@Article=": "article",
        "& @Article=": "article",
    }

    for raw_line in lines:
        line = raw_line.strip()

        for marker, field_name in marker_map.items():
            if not line.startswith(marker):
                continue

            value = line[len(marker):].strip()

            # Some source records put Short and Article
            # on the same tab-separated line.
            if (
                field_name == "short_description"
                and re.search(r"\s*&\s*@Article=", value)
            ):
                short_value, article_value = re.split(
                    r"\s*&\s*@Article=",
                    value,
                    maxsplit=1,
                )

                descriptions["short_description"] = clean_text(
                    short_value
                )
                descriptions["article"] = clean_text(
                    article_value
                )
            else:
                descriptions[field_name] = clean_text(value)

            break

    return descriptions


def category_from_heading(heading):
    normalized = heading.strip().upper()

    for prefix, category in CATEGORY_MAP.items():
        if normalized.startswith(prefix):
            return category

    return None


def make_details(category, columns):
    details = {
        "source_fields": [
            clean_text(value)
            for value in columns[1:-2]
        ],
    }

    if category == ProperName.Category.PERSON:
        names = (
            "parents",
            "siblings",
            "partners",
            "offspring",
            "tribe_or_nation",
        )

        for index, name in enumerate(names, start=2):
            if index < len(columns) - 2:
                details[name] = clean_text(columns[index])

    elif category == ProperName.Category.PLACE:
        names = (
            "open_bible_name",
            "founder_or_origin",
            "people",
            "google_maps_url",
            "palopenmaps_url",
            "geographical_area",
        )

        for index, name in enumerate(names, start=1):
            if index < len(columns) - 2:
                details[name] = clean_text(columns[index])

    return details


class Command(BaseCommand):
    help = "Import STEPBible TIPNR proper-name records."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Path to the TIPNR text file.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        text = path.read_text(encoding="utf-8-sig")
        text = text.replace("\r\n", "\n")

        blocks = text.split("$==========")

        proper_names = []
        counts = Counter()
        seen_keys = set()
        duplicate_keys = []

        for block in blocks:
            lines = [
                line.rstrip()
                for line in block.splitlines()
                if line.strip()
            ]

            if len(lines) < 2:
                continue

            category = category_from_heading(lines[0])

            if not category:
                continue

            summary_columns = split_columns(lines[1])

            if not summary_columns:
                continue

            entry_key = summary_columns[0].strip()

            # Documentation examples are ignored. A real record
            # has a key such as Aaron@Exo.4.14-Heb=H0175.
            if (
                "@" not in entry_key
                or not re.search(r"=[HG]\d", entry_key)
            ):
                continue

            if entry_key in seen_keys:
                duplicate_keys.append(entry_key)
                continue

            seen_keys.add(entry_key)

            display_name = clean_text(
                entry_key.split("@", 1)[0]
            )

            description = (
                clean_text(summary_columns[1])
                if len(summary_columns) > 1
                else ""
            )

            summary = (
                clean_text(summary_columns[-2])
                if len(summary_columns) >= 3
                else ""
            )

            entry_type = (
                clean_text(summary_columns[-1])
                if len(summary_columns) >= 2
                else ""
            )

            forms = []
            all_names = ""
            strong_numbers = ""
            total_references = []

            for line in lines[2:]:
                stripped_line = line.lstrip()

                if not re.match(r"^[–-]\s*", stripped_line):
                    continue

                columns = split_columns(stripped_line)

                if not columns:
                    continue

                significance = re.sub(
                    r"^[–-]\s*",
                    "",
                    columns[0],
                ).strip()

                if significance.casefold() == "total":
                    all_names = (
                        clean_text(columns[1])
                        if len(columns) > 1
                        else ""
                    )
                    strong_numbers = (
                        clean_text(columns[2])
                        if len(columns) > 2
                        else ""
                    )
                    total_references = (
                        parse_references(columns[3])
                        if len(columns) > 3
                        else []
                    )
                    continue

                form = {
                    "significance": clean_text(significance),
                    "unique_name": (
                        clean_text(columns[1])
                        if len(columns) > 1
                        else ""
                    ),
                    "strong_expression": (
                        clean_text(columns[2])
                        if len(columns) > 2
                        else ""
                    ),
                    "translated_name": (
                        clean_text(columns[3])
                        if len(columns) > 3
                        else ""
                    ),
                    "stepbible_url": (
                        columns[4].strip()
                        if len(columns) > 4
                        else ""
                    ),
                    "references": (
                        parse_references(columns[5])
                        if len(columns) > 5
                        else []
                    ),
                }

                forms.append(form)

            if not total_references:
                for form in forms:
                    for reference in form["references"]:
                        if reference not in total_references:
                            total_references.append(reference)

            descriptions = parse_descriptions(lines[2:])

            proper_names.append(
                ProperName(
                    category=category,
                    entry_key=entry_key,
                    display_name=display_name,
                    description=description,
                    entry_type=entry_type,
                    summary=summary,
                    briefest=descriptions["briefest"],
                    brief=descriptions["brief"],
                    short_description=descriptions[
                        "short_description"
                    ],
                    article=descriptions["article"],
                    all_names=all_names,
                    strong_numbers=strong_numbers,
                    references=total_references,
                    forms=forms,
                    details=make_details(
                        category,
                        summary_columns,
                    ),
                )
            )

            counts[category] += 1

        if duplicate_keys:
            raise CommandError(
                "Duplicate TIPNR entry keys found:\n"
                + "\n".join(duplicate_keys[:30])
            )

        if not proper_names:
            raise CommandError(
                "No real TIPNR records were detected."
            )

        missing_categories = [
            category
            for category in CATEGORY_MAP.values()
            if counts[category] == 0
        ]

        if missing_categories:
            raise CommandError(
                "No records found for categories: "
                + ", ".join(missing_categories)
            )

        with transaction.atomic():
            ProperName.objects.all().delete()

            ProperName.objects.bulk_create(
                proper_names,
                batch_size=1000,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "TIPNR proper names imported successfully."
            )
        )
        self.stdout.write(
            f"Persons: {counts[ProperName.Category.PERSON]}"
        )
        self.stdout.write(
            f"Places: {counts[ProperName.Category.PLACE]}"
        )
        self.stdout.write(
            f"Other: {counts[ProperName.Category.OTHER]}"
        )
        self.stdout.write(f"Total: {len(proper_names)}")
        self.stdout.write(
            "Source: STEPBible TIPNR, CC BY 4.0"
        )
