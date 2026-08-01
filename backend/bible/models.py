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
