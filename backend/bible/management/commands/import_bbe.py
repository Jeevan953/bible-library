import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bible.models import BibleVersion, Verse, VerseText


FILE_PATTERN = re.compile(
     r"^engBBE_\d{3}_(?P<code>[A-Z0-9]+)_"
     r"(?P<chapter>\d+)_read\.txt$"
)

BOOK_CODES = (
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
    "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
    "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
    "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
    "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT",
    "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL",
    "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT",
    "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN",
    "JUD", "REV",
)

BOOK_POSITIONS = {
    code: position
    for position, code in enumerate(BOOK_CODES, start=1)
}

OMITTED_VERSES = {
    ("MAT", 17, 21),
    ("MAT", 18, 11),
    ("MAT", 23, 14),
    ("MRK", 7, 16),
    ("MRK", 9, 44),
    ("MRK", 9, 46),
    ("MRK", 11, 26),
    ("MRK", 15, 28),
    ("LUK", 17, 36),
    ("LUK", 23, 17),
    ("JHN", 5, 4),
    ("ACT", 8, 37),
    ("ACT", 15, 34),
    ("ACT", 24, 7),
    ("ACT", 28, 29),
    ("ROM", 16, 24),
}


class Command(BaseCommand):
    help = "Import chapter-wise Bible in Basic English text files."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str)

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        files = list(folder.glob("*_read.txt"))

        if len(files) != 1189:
            raise CommandError(
                f"Expected 1189 chapter files, found {len(files)}"
            )

        def file_key(path):
            match = FILE_PATTERN.match(path.name)

            if not match:
                raise CommandError(
                    f"Unexpected filename: {path.name}"
                )

            return (
                BOOK_POSITIONS[match.group("code")],
                int(match.group("chapter")),
            )

        files.sort(key=file_key)

        verse_texts = []
        books_seen = set()
        chapters_seen = set()
        errors = []

        for path in files:
            match = FILE_PATTERN.match(path.name)

            book_code = match.group("code")
            book_position = BOOK_POSITIONS[book_code]
            chapter_number = int(match.group("chapter"))

            lines = [
                line.strip()
                for line in path.read_text(
                    encoding="utf-8-sig"
                ).splitlines()
                if line.strip()
            ]

            if len(lines) < 3:
                errors.append(f"{path.name}: no verse text")
                continue

            # First two non-empty lines are book/chapter headings.
            texts = lines[2:]

            verses = list(
                Verse.objects.filter(
                    chapter__book__position=book_position,
                    chapter__number=chapter_number,
                ).order_by("number")
            )

            import_verses = [
                verse
                for verse in verses
                if (
                    book_code,
                    chapter_number,
                    verse.number,
                )
                not in OMITTED_VERSES
            ]

            if not verses:
                errors.append(
                    f"{path.name}: canonical chapter not found"
                )
                continue

            if len(texts) != len(import_verses):
                errors.append(
                    f"{path.name}: expected {len(import_verses)} verses, "
                    f"found {len(texts)}"
                )
                continue

            books_seen.add(book_position)
            chapters_seen.add(
                (book_position, chapter_number)
            )

            for verse, text in zip(import_verses, texts):
                verse_texts.append(
                    VerseText(verse=verse, text=text)
                )

        if errors:
            preview = "\n".join(errors[:30])
            raise CommandError(
                f"BBE validation failed:\n{preview}\n"
                f"Total errors: {len(errors)}"
            )

        with transaction.atomic():
            version, _ = BibleVersion.objects.get_or_create(
                abbreviation="BBE",
                defaults={
                    "name": "Bible in Basic English",
                    "language": "English",
                },
            )

            version.name = "Bible in Basic English"
            version.language = "English"
            version.pdf_filename = "BBE.pdf"
            version.save()

            for item in verse_texts:
                item.bible_version = version

            VerseText.objects.bulk_create(
                verse_texts,
                batch_size=1000,
                update_conflicts=True,
                update_fields=["text"],
                unique_fields=["bible_version", "verse"],
            )

        self.stdout.write(
            self.style.SUCCESS(
                "\n".join(
                    [
                        "Updated: Bible in Basic English (BBE)",
                        f"Books: {len(books_seen)}",
                        f"Chapters: {len(chapters_seen)}",
                        f"Verses: {len(verse_texts)}",
                    ]
                )
            )
        )
