from rest_framework import serializers
from bible.models import BibleVersion, VerseText, Book, Chapter

class BibleVersionSerializer(serializers.ModelSerializer):
    verse_count = serializers.SerializerMethodField()
    
    class Meta:
        model = BibleVersion
        fields = ['id', 'abbreviation', 'name', 'language', 'year', 
                 'description', 'verse_count']
    
    def get_verse_count(self, obj):
        return obj.verse_texts.count()

class VerseTextSerializer(serializers.ModelSerializer):
    version = serializers.CharField(source='bible_version.abbreviation')
    book = serializers.CharField(source='verse.chapter.book.name')
    book_slug = serializers.CharField(source='verse.chapter.book.slug')
    chapter = serializers.IntegerField(source='verse.chapter.number')
    verse = serializers.IntegerField(source='verse.number')
    
    class Meta:
        model = VerseText
        fields = ['id', 'version', 'book', 'book_slug', 'chapter', 'verse', 'text']

class BookSerializer(serializers.ModelSerializer):
    chapter_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Book
        fields = ['id', 'name', 'slug', 'position', 'chapter_count']
    
    def get_chapter_count(self, obj):
        return obj.chapters.count()

class ChapterSerializer(serializers.ModelSerializer):
    book = serializers.CharField(source='book.name')
    verse_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Chapter
        fields = ['id', 'book', 'number', 'verse_count']
    
    def get_verse_count(self, obj):
        return obj.verses.count()