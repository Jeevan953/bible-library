from rest_framework import serializers

from .models import BibleVersion, Book

from bible.models import BibleVersion, VerseText
from rest_framework import serializers

class BibleVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BibleVersion
        fields = ['id', 'abbreviation', 'name', 'language', 'year', 'description']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Add verse count
        data['verse_count'] = VerseText.objects.filter(bible_version=instance).count()
        return data


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
