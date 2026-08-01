import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Book, Verse, VerseText


class Command(BaseCommand):
    help = "Import A Conservative Version from ACV JSON."

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str)

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])

        if not json_path.is_file():
            raise CommandError(
                f"JSON file not found: {json_path}"
            )

        data = json.loads(
            json_path.read_text(encoding="utf-8")
        )

        books_data = data.get("books", [])

        if len(books_data) != 66:
            raise CommandError(
                f"Expected 66 books, found {len(books_data)}"
            )

        imported_texts = []
        chapter_count = 0
        errors = []

        for position, book_data in enumerate(
            books_data,
            start=1,
        ):
            try:
                canonical_book = Book.objects.get(
                    position=position
                )
            except Book.DoesNotExist:
                errors.append(
                    f"Canonical book position {position} not found"
                )
                continue

            for chapter_data in book_data.get(
                "chapters",
                [],
            ):
                chapter_number = int(
                    chapter_data["chapter"]
                )
                chapter_count += 1

                canonical_verses = list(
                    Verse.objects.filter(
                        chapter__book=canonical_book,
                        chapter__number=chapter_number,
                    ).order_by("number")
                )

                json_verses = {}

                for item in chapter_data.get("verses", []):
                    number = int(item["verse"])
                    text = str(
                        item.get("text", "")
                    ).strip()

                    if not text:
                        errors.append(
                            f"{canonical_book.name} "
                            f"{chapter_number}:{number} is empty"
                        )

                    if number in json_verses:
                        errors.append(
                            f"{canonical_book.name} "
                            f"{chapter_number}:{number} duplicated"
                        )

                    json_verses[number] = text

                expected = {
                    verse.number
                    for verse in canonical_verses
                }
                actual = set(json_verses)

                if expected != actual:
                    errors.append(
                        f"{canonical_book.name} "
                        f"{chapter_number}: "
                        f"missing={sorted(expected - actual)}, "
                        f"extra={sorted(actual - expected)}"
                    )
                    continue

                for verse in canonical_verses:
                    imported_texts.append(
                        (
                            verse,
                            json_verses[verse.number],
                        )
                    )

        if errors:
            raise CommandError(
                "ACV validation failed:\n"
                + "\n".join(errors[:30])
                + f"\nTotal errors: {len(errors)}"
            )

        if chapter_count != 1189:
            raise CommandError(
                f"Expected 1189 chapters, "
                f"found {chapter_count}"
            )

        if len(imported_texts) != 31102:
            raise CommandError(
                f"Expected 31102 verses, "
                f"found {len(imported_texts)}"
            )

        with transaction.atomic():
            version, _ = BibleVersion.objects.get_or_create(
                abbreviation="ACV",
                defaults={
                    "name": "A Conservative Version",
                    "language": "English",
                },
            )

            version.name = "A Conservative Version"
            version.language = "English"
            version.description = (
                "Imported from the complete ACV JSON text."
            )
            version.pdf_filename = "ACV.pdf"
            version.save()

            verse_text_objects = [
                VerseText(
                    bible_version=version,
                    verse=verse,
                    text=text,
                )
                for verse, text in imported_texts
            ]

            VerseText.objects.bulk_create(
                verse_text_objects,
                batch_size=1000,
                update_conflicts=True,
                update_fields=["text"],
                unique_fields=[
                    "bible_version",
                    "verse",
                ],
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\n".join(
                    [
                        "Updated: A Conservative Version (ACV)",
                        "Books: 66",
                        f"Chapters: {chapter_count}",
                        f"Verses: {len(imported_texts)}",
                    ]
                )
            )
        )
