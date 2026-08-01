from rest_framework import serializers

from .models import BibleVersion, Book


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
        return obj.verse_texts.exists()


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = [
            "id",
            "name",
            "slug",
            "position",
        ]
