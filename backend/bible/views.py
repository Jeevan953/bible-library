from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from rest_framework.exceptions import (
    NotFound,
    ValidationError,
)
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    BibleVersion,
    Book,
    Chapter,
    Verse,
    VerseText,
)
from .serializers import BibleVersionSerializer, BookSerializer


class BibleVersionListAPIView(ListAPIView):
    queryset = BibleVersion.objects.order_by("name")
    serializer_class = BibleVersionSerializer


class BibleVersionBookListAPIView(APIView):
    def get(self, request, abbreviation):
        version = get_object_or_404(
            BibleVersion,
            abbreviation__iexact=abbreviation,
        )

        books = (
            Book.objects.filter(
                chapters__verses__translations__bible_version=version
            )
            .distinct()
            .order_by("position")
        )

        return Response(
            {
                "version": BibleVersionSerializer(version).data,
                "books": BookSerializer(books, many=True).data,
            }
        )


class BibleVersionChapterListAPIView(APIView):
    def get(self, request, abbreviation, book_position):
        version = get_object_or_404(
            BibleVersion,
            abbreviation__iexact=abbreviation,
        )

        book = get_object_or_404(
            Book,
            position=book_position,
        )

        chapters = (
            Chapter.objects.filter(
                book=book,
                verses__translations__bible_version=version,
            )
            .distinct()
            .order_by("number")
            .values_list("number", flat=True)
        )

        return Response(
            {
                "version": BibleVersionSerializer(version).data,
                "book": BookSerializer(book).data,
                "chapters": list(chapters),
            }
        )


class ChapterReaderAPIView(APIView):
    def get(
        self,
        request,
        abbreviation,
        book_position,
        chapter_number,
    ):
        version = get_object_or_404(
            BibleVersion,
            abbreviation__iexact=abbreviation,
        )

        book = get_object_or_404(
            Book,
            position=book_position,
        )

        chapter = get_object_or_404(
            Chapter,
            book=book,
            number=chapter_number,
        )

        verse_texts = (
            VerseText.objects.filter(
                bible_version=version,
                verse__chapter=chapter,
            )
            .select_related("verse")
            .order_by("verse__number")
        )

        if not verse_texts.exists():
            raise NotFound(
                f"{book.name} {chapter_number} is not "
                f"available in {version.abbreviation}."
            )

        verses = [
            {
                "number": verse_text.verse.number,
                "text": verse_text.text,
            }
            for verse_text in verse_texts
        ]

        return Response(
            {
                "version": BibleVersionSerializer(version).data,
                "book": BookSerializer(book).data,
                "chapter": chapter.number,
                "verses": verses,
            }
        )

class ParallelChapterAPIView(APIView):
    def get(
        self,
        request,
        book_position,
        chapter_number,
    ):
        book = get_object_or_404(
            Book,
            position=book_position,
        )

        chapter = get_object_or_404(
            Chapter,
            book=book,
            number=chapter_number,
        )

        requested = request.query_params.get(
            "versions",
            "",
        )

        if requested:
            abbreviations = list(
                dict.fromkeys(
                    abbreviation.strip().upper()
                    for abbreviation in requested.split(",")
                    if abbreviation.strip()
                )
            )

            version_lookup = {
                version.abbreviation: version
                for version in BibleVersion.objects.filter(
                    abbreviation__in=abbreviations
                )
            }

            unknown = [
                abbreviation
                for abbreviation in abbreviations
                if abbreviation not in version_lookup
            ]

            if unknown:
                raise NotFound(
                    f"Unknown versions: {', '.join(unknown)}"
                )

            versions = [
                version_lookup[abbreviation]
                for abbreviation in abbreviations
            ]
        else:
            versions = list(
                BibleVersion.objects.filter(
                    verse_texts__isnull=False
                )
                .distinct()
                .order_by("name")
            )

        selected_texts = (
            VerseText.objects.filter(
                bible_version__in=versions
            )
            .select_related("bible_version")
        )

        verses = (
            Verse.objects.filter(chapter=chapter)
            .order_by("number")
            .prefetch_related(
                Prefetch(
                    "translations",
                    queryset=selected_texts,
                    to_attr="parallel_texts",
                )
            )
        )

        verse_rows = []

        for verse in verses:
            texts = {
                version.abbreviation: None
                for version in versions
            }

            for verse_text in verse.parallel_texts:
                texts[
                    verse_text.bible_version.abbreviation
                ] = verse_text.text

            verse_rows.append(
                {
                    "number": verse.number,
                    "texts": texts,
                }
            )

        return Response(
            {
                "book": BookSerializer(book).data,
                "chapter": chapter.number,
                "versions": BibleVersionSerializer(
                    versions,
                    many=True,
                ).data,
                "verses": verse_rows,
            }
        )

class BibleSearchAPIView(APIView):
    def get(self, request):
        query = request.query_params.get(
            "q",
            "",
        ).strip()

        abbreviation = request.query_params.get(
            "version",
            "KJV",
        ).strip().upper()

        if not query:
            raise ValidationError(
                {"q": "Enter a word or phrase to search."}
            )

        try:
            page = int(
                request.query_params.get("page", "1")
            )
        except ValueError:
            raise ValidationError(
                {"page": "Page must be a number."}
            )

        if page < 1:
            raise ValidationError(
                {"page": "Page must be at least 1."}
            )

        version = get_object_or_404(
            BibleVersion,
            abbreviation__iexact=abbreviation,
        )

        matches = (
            VerseText.objects.filter(
                bible_version=version,
                text__icontains=query,
            )
            .select_related(
                "verse__chapter__book"
            )
            .order_by(
                "verse__chapter__book__position",
                "verse__chapter__number",
                "verse__number",
            )
        )

        page_size = 50
        total_results = matches.count()
        total_pages = max(
            1,
            (
                total_results + page_size - 1
            ) // page_size,
        )

        start = (page - 1) * page_size
        end = start + page_size

        results = []

        for match in matches[start:end]:
            verse = match.verse
            chapter = verse.chapter
            book = chapter.book

            results.append(
                {
                    "reference": (
                        f"{book.name} "
                        f"{chapter.number}:"
                        f"{verse.number}"
                    ),
                    "book": {
                        "id": book.id,
                        "name": book.name,
                        "position": book.position,
                        "slug": book.slug,
                    },
                    "chapter": chapter.number,
                    "verse": verse.number,
                    "text": match.text,
                }
            )

        return Response(
            {
                "query": query,
                "version": (
                    BibleVersionSerializer(version).data
                ),
                "count": total_results,
                "page": page,
                "total_pages": total_pages,
                "results": results,
            }
        )