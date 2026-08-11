from rest_framework import serializers

from .models import BibleVersion, Book


# These translations must remain inaccessible until written
# permission and implementation guidance are received.
PUBLICLY_DISABLED_ABBREVIATIONS = frozenset({
    "AFV",
    "ESV",
    "NASB",
})


class BibleVersionSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()

    class Meta:
        model = BibleVersion
        fields = [
            "id",
            "name",
            "abbreviation",
            "language",
            "year",
            "description",
            "pdf_filename",
            "available",
        ]

    def get_available(self, obj):
        return (
            obj.abbreviation.upper()
            not in PUBLICLY_DISABLED_ABBREVIATIONS
            and obj.verse_texts.exists()
        )


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = [
            "id",
            "name",
            "slug",
            "position",
        ]
