import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


FILE_PATTERN = re.compile(
    r"^peter_percival_1856_genesis_(\d+)_review\.json$"
)


class Command(BaseCommand):
    help = "Import Peter Percival Tamil Genesis draft JSON files."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)
        parser.add_argument(
            "--allow-draft",
            action="store_true",
            help="Explicitly permit importing unreviewed draft verses.",
        )

    def handle(self, *args, **options):
        if not options["allow_draft"]:
            raise CommandError(
                "These files are drafts. Add --allow-draft "
                "to import them for local preview."
            )

        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        files = []

        for path in folder.glob(
            "peter_percival_1856_genesis_*_review.json"
        ):
            match = FILE_PATTERN.match(path.name)

            if match:
                files.append((int(match.group(1)), path))

        files.sort(key=lambda item: item[0])

        if len(files) != 50:
            raise CommandError(
                f"Expected 50 Genesis files, found {len(files)}"
            )

        verse_texts = []
        errors = []

        for filename_chapter, path in files:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )

            chapter_number = int(data.get("chapter", 0))

            if data.get("book") != "Genesis":
                errors.append(
                    f"{path.name}: book is not Genesis"
                )
                continue

            if chapter_number != filename_chapter:
                errors.append(
                    f"{path.name}: chapter metadata mismatch"
                )
                continue

            canonical_verses = list(
                Verse.objects.filter(
                    chapter__book__position=1,
                    chapter__number=chapter_number,
                ).order_by("number")
            )

            json_verses = {}

            for item in data.get("verses", []):
                number = int(item["number"])
                text = str(item.get("text", "")).strip()

                if number in json_verses:
                    errors.append(
                        f"{path.name}: duplicate verse {number}"
                    )

                if not text:
                    errors.append(
                        f"{path.name}: empty verse {number}"
                    )

                json_verses[number] = text

            expected_numbers = {
                verse.number for verse in canonical_verses
            }
            actual_numbers = set(json_verses)

            if expected_numbers != actual_numbers:
                missing = sorted(
                    expected_numbers - actual_numbers
                )
                extra = sorted(
                    actual_numbers - expected_numbers
                )

                errors.append(
                    f"{path.name}: missing={missing}, extra={extra}"
                )
                continue

            for verse in canonical_verses:
                verse_texts.append(
                    VerseText(
                        verse=verse,
                        text=json_verses[verse.number],
                    )
                )

        if errors:
            raise CommandError(
                "Tamil validation failed:\n"
                + "\n".join(errors[:30])
                + f"\nTotal errors: {len(errors)}"
            )

        if len(verse_texts) != 1533:
            raise CommandError(
                f"Expected 1533 verses, found {len(verse_texts)}"
            )

        with transaction.atomic():
            version, _ = BibleVersion.objects.get_or_create(
                abbreviation="PPTB1856",
                defaults={
                    "name": "Peter Percival Tamil Bible (Draft)",
                    "language": "Tamil",
                    "year": 1856,
                },
            )

            version.name = "Peter Percival Tamil Bible (Draft)"
            version.language = "Tamil"
            version.year = 1856
            version.description = (
                "Draft transcription. Genesis chapters 1-50. "
                "Verses require visual review against the PDF."
            )
            version.pdf_filename = (
                "Tamil Bible-Peter-Percival-Genesis-&-Exodus.pdf"
            )
            version.save()

            for item in verse_texts:
                item.bible_version = version

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=500,
                update_conflicts=True,
                update_fields=["text"],
                unique_fields=["bible_version", "verse"],
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\n".join(
                    [
                        "Updated: Peter Percival Tamil Bible (Draft)",
                        "Books: 1",
                        "Chapters: 50",
                        f"Verses: {len(verse_texts)}",
                    ]
                )
            )
        )
