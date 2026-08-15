from django.db import models


class BibleVersion(models.Model):
    name = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=30, unique=True)
    language = models.CharField(max_length=100, default="English")
    year = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    pdf_filename = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class Book(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    position = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.name


class Chapter(models.Model):
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="chapters",
    )
    number = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["book__position", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["book", "number"],
                name="unique_chapter_per_book",
            )
        ]

    def __str__(self):
        return f"{self.book.name} {self.number}"


class Verse(models.Model):
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        related_name="verses",
    )
    number = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["chapter", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["chapter", "number"],
                name="unique_verse_per_chapter",
            )
        ]

    def __str__(self):
        return f"{self.chapter}:{self.number}"


class VerseText(models.Model):
    bible_version = models.ForeignKey(
        BibleVersion,
        on_delete=models.CASCADE,
        related_name="verse_texts",
    )
    verse = models.ForeignKey(
        Verse,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    text = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bible_version", "verse"],
                name="unique_text_per_version_and_verse",
            )
        ]
        indexes = [
            models.Index(fields=["bible_version", "verse"]),
        ]

    def __str__(self):
        return f"{self.bible_version.abbreviation} — {self.verse}"

class TamilDictionaryEntry(models.Model):
    word = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )
    definition = models.TextField()

    class Meta:
        ordering = ["word"]
        verbose_name = "Tamil dictionary entry"
        verbose_name_plural = "Tamil dictionary entries"

    def __str__(self):
        return self.word


class ProperName(models.Model):
    class Category(models.TextChoices):
        PERSON = "PERSON", "Person"
        PLACE = "PLACE", "Place"
        OTHER = "OTHER", "Other"

    category = models.CharField(
        max_length=10,
        choices=Category.choices,
        db_index=True,
    )

    # Example: Aaron@Exo.4.14-Heb=H0175
    entry_key = models.CharField(
        max_length=300,
        unique=True,
    )

    display_name = models.CharField(
        max_length=200,
        db_index=True,
    )

    description = models.TextField(blank=True)
    entry_type = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )
    summary = models.TextField(blank=True)

    briefest = models.TextField(blank=True)
    brief = models.TextField(blank=True)
    short_description = models.TextField(blank=True)
    article = models.TextField(blank=True)

    all_names = models.TextField(blank=True)
    strong_numbers = models.TextField(blank=True)

    # Normalized reference strings such as:
    # ["Job.26.6", "Job.28.22", "Rev.9.11"]
    references = models.JSONField(
        default=list,
        blank=True,
    )

    # Every “Named”, “Greek”, “Variant”, etc. sub-record.
    forms = models.JSONField(
        default=list,
        blank=True,
    )

    # Family relationships, map links and other category fields.
    details = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["display_name", "entry_key"]
        indexes = [
            models.Index(
                fields=["category", "display_name"],
                name="proper_name_category_name",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.category})"


class HitchcockName(models.Model):
    source_id = models.CharField(
        max_length=64,
        unique=True,
    )
    name = models.CharField(
        max_length=200,
        db_index=True,
    )
    definition = models.TextField()

    class Meta:
        ordering = ["name", "source_id"]
        verbose_name = "Hitchcock Bible name"
        verbose_name_plural = "Hitchcock Bible names"

    def __str__(self):
        return self.name
