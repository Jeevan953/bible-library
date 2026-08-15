import re

from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
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
    HitchcockName,
    ProperName,
    TamilDictionaryEntry,
    Verse,
    VerseText,
)
from .serializers import (
    PUBLICLY_DISABLED_ABBREVIATIONS,
    BibleVersionSerializer,
    BookSerializer,
)


def get_public_version_or_404(abbreviation):
    version = get_object_or_404(
        BibleVersion,
        abbreviation__iexact=abbreviation,
    )

    if (
        version.abbreviation.upper()
        in PUBLICLY_DISABLED_ABBREVIATIONS
    ):
        raise NotFound(
            f"{version.abbreviation} is not publicly available."
        )

    return version


class BibleVersionListAPIView(ListAPIView):
    # React expects /api/versions/ to return a plain JSON array.
    pagination_class = None
    queryset = BibleVersion.objects.order_by("name")
    serializer_class = BibleVersionSerializer


class BibleVersionBookListAPIView(APIView):
    def get(self, request, abbreviation):
        version = get_public_version_or_404(
            abbreviation
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
        version = get_public_version_or_404(
            abbreviation
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
        version = get_public_version_or_404(
            abbreviation
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

            restricted = [
                abbreviation
                for abbreviation in abbreviations
                if abbreviation
                in PUBLICLY_DISABLED_ABBREVIATIONS
            ]

            if restricted:
                raise NotFound(
                    "Versions are not publicly available: "
                    f"{', '.join(restricted)}"
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
                .exclude(
                    abbreviation__in=(
                        PUBLICLY_DISABLED_ABBREVIATIONS
                    )
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

REFERENCE_PATTERN = re.compile(
    r"^(?P<book>.+?)\s+"
    r"(?P<chapter>\d+)"
    r"(?:\s*:\s*(?P<verse>\d+))?$",
    re.IGNORECASE,
)

REFERENCE_BOOK_ALIASES = {
    "gen": "Genesis",
    "exo": "Exodus",
    "exod": "Exodus",
    "lev": "Leviticus",
    "num": "Numbers",
    "deu": "Deuteronomy",
    "deut": "Deuteronomy",
    "jos": "Joshua",
    "josh": "Joshua",
    "jdg": "Judges",
    "judg": "Judges",
    "rut": "Ruth",
    "ps": "Psalms",
    "psa": "Psalms",
    "psalm": "Psalms",
    "pro": "Proverbs",
    "prov": "Proverbs",
    "ecc": "Ecclesiastes",
    "isa": "Isaiah",
    "jer": "Jeremiah",
    "ezk": "Ezekiel",
    "dan": "Daniel",
    "mat": "Matthew",
    "matt": "Matthew",
    "mrk": "Mark",
    "mk": "Mark",
    "luk": "Luke",
    "lk": "Luke",
    "jhn": "John",
    "jn": "John",
    "joh": "John",
    "act": "Acts",
    "rom": "Romans",
    "rev": "Revelation",
}


def parse_scripture_reference(query):
    match = REFERENCE_PATTERN.fullmatch(query.strip())

    if not match:
        return None

    book_term = " ".join(
        match.group("book").split()
    )
    alias_key = re.sub(
        r"[^a-z0-9]",
        "",
        book_term.lower(),
    )
    canonical_name = REFERENCE_BOOK_ALIASES.get(
        alias_key,
        book_term,
    )
    slug_term = re.sub(
        r"[^a-z0-9]+",
        "-",
        canonical_name.lower(),
    ).strip("-")

    book = (
        Book.objects.filter(
            Q(name__iexact=canonical_name)
            | Q(slug__iexact=slug_term)
        )
        .order_by("position")
        .first()
    )

    if book is None:
        return None

    return {
        "book": book,
        "chapter": int(match.group("chapter")),
        "verse": (
            int(match.group("verse"))
            if match.group("verse")
            else None
        ),
    }


class BibleSearchAPIView(APIView):
    page_size = 50

    def get_page_number(self, request):
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

        return page

    def get(self, request):
        query = request.query_params.get(
            "q",
            "",
        ).strip()

        search_mode = request.query_params.get(
            "version",
            "KJV",
        ).strip().upper()

        if not query:
            raise ValidationError(
                {"q": "Enter a word, phrase, or reference."}
            )

        page = self.get_page_number(request)

        if search_mode == "PROPER_NAMES":
            return self.search_proper_names(
                query,
                page,
            )

        if search_mode == "HITCHCOCK_NAMES":
            return self.search_hitchcock_names(
                query,
                page,
            )

        if search_mode == "TAMIL_DICTIONARY":
            return self.search_tamil_dictionary(
                query,
                page,
            )

        return self.search_scripture(
            query,
            search_mode,
            page,
        )

    def search_tamil_dictionary(
        self,
        query,
        page,
    ):
        matches = (
            TamilDictionaryEntry.objects.filter(
                Q(word__icontains=query)
                | Q(definition__icontains=query)
            )
            .order_by("word")
        )

        total_results = matches.count()
        total_pages = max(
            1,
            (
                total_results + self.page_size - 1
            ) // self.page_size,
        )

        start = (page - 1) * self.page_size
        end = start + self.page_size

        results = [
            {
                "result_type": "tamil_dictionary",
                "id": entry.id,
                "word": entry.word,
                "definition": entry.definition,
            }
            for entry in matches[start:end]
        ]

        return Response(
            {
                "query": query,
                "mode": "tamil_dictionary",
                "search_type": "tamil_dictionary",
                "version": None,
                "count": total_results,
                "page": page,
                "total_pages": total_pages,
                "results": results,
                "attribution": {
                    "name": "Tamil Bible Dictionary",
                    "abbreviation": "TAMDIC",
                    "creator": "Yesudas Solomon",
                    "publisher": (
                        "Word of God Ministries"
                    ),
                    "license": (
                        "Free of Cost and "
                        "Non-Profitable reasons only"
                    ),
                    "url": "http://www.WordOfGod.in",
                },
            }
        )

    def search_hitchcock_names(self, query, page):
        matches = (
            HitchcockName.objects.filter(
                Q(name__icontains=query)
                | Q(definition__icontains=query)
            )
            .order_by("name", "source_id")
        )

        total_results = matches.count()
        total_pages = max(
            1,
            (
                total_results + self.page_size - 1
            ) // self.page_size,
        )

        start = (page - 1) * self.page_size
        end = start + self.page_size

        results = [
            {
                "result_type": "hitchcock_name",
                "id": entry.id,
                "source_id": entry.source_id,
                "name": entry.name,
                "definition": entry.definition,
            }
            for entry in matches[start:end]
        ]

        return Response(
            {
                "query": query,
                "mode": "hitchcock_names",
                "search_type": "hitchcock_names",
                "version": None,
                "count": total_results,
                "page": page,
                "total_pages": total_pages,
                "results": results,
                "attribution": {
                    "name": (
                        "Hitchcock's Bible Names Dictionary"
                    ),
                    "creator": "Roswell D. Hitchcock",
                    "original_publication": 1869,
                    "electronic_source": (
                        "Christian Classics Ethereal Library"
                    ),
                    "rights": "Public Domain",
                    "url": (
                        "https://www.ccel.org/ccel/"
                        "hitchcock/bible_names.html"
                    ),
                },
            }
        )

    def search_proper_names(self, query, page):
        matches = (
            ProperName.objects.filter(
                Q(display_name__icontains=query)
                | Q(entry_key__icontains=query)
                | Q(all_names__icontains=query)
                | Q(strong_numbers__icontains=query)
                | Q(description__icontains=query)
                | Q(brief__icontains=query)
                | Q(short_description__icontains=query)
            )
            .order_by(
                "display_name",
                "category",
                "entry_key",
            )
        )

        total_results = matches.count()
        total_pages = max(
            1,
            (
                total_results + self.page_size - 1
            ) // self.page_size,
        )

        start = (page - 1) * self.page_size
        end = start + self.page_size

        results = []

        for proper_name in matches[start:end]:
            results.append(
                {
                    "result_type": "proper_name",
                    "id": proper_name.id,
                    "name": proper_name.display_name,
                    "category": proper_name.category,
                    "type": proper_name.entry_type,
                    "description": (
                        proper_name.brief
                        or proper_name.short_description
                        or proper_name.description
                        or proper_name.summary
                    ),
                    "briefest": proper_name.briefest,
                    "short_description": (
                        proper_name.short_description
                    ),
                    "all_names": proper_name.all_names,
                    "strong_numbers": (
                        proper_name.strong_numbers
                    ),
                    "references": proper_name.references,
                    "forms": proper_name.forms,
                }
            )

        return Response(
            {
                "query": query,
                "mode": "proper_names",
                "search_type": "proper_names",
                "version": None,
                "count": total_results,
                "page": page,
                "total_pages": total_pages,
                "results": results,
                "attribution": {
                    "name": "STEPBible TIPNR",
                    "license": "CC BY 4.0",
                    "url": (
                        "https://github.com/"
                        "STEPBible/STEPBible-Data"
                    ),
                },
            }
        )

    def search_scripture(
        self,
        query,
        search_mode,
        page,
    ):
        all_versions = search_mode == "ALL"

        if all_versions:
            version = None
        else:
            version = get_public_version_or_404(
                search_mode
            )

        reference = parse_scripture_reference(query)

        matches = VerseText.objects.exclude(
            bible_version__abbreviation__in=(
                PUBLICLY_DISABLED_ABBREVIATIONS
            )
        )

        if version is not None:
            matches = matches.filter(
                bible_version=version
            )

        if reference is not None:
            matches = matches.filter(
                verse__chapter__book=reference["book"],
                verse__chapter__number=(
                    reference["chapter"]
                ),
            )

            if reference["verse"] is not None:
                matches = matches.filter(
                    verse__number=reference["verse"]
                )

            search_type = "reference"
        else:
            matches = matches.filter(
                text__icontains=query
            )
            search_type = "text"

        matches = (
            matches.select_related(
                "bible_version",
                "verse__chapter__book",
            )
            .order_by(
                "verse__chapter__book__position",
                "verse__chapter__number",
                "verse__number",
                "bible_version__name",
            )
        )

        total_results = matches.count()
        total_pages = max(
            1,
            (
                total_results + self.page_size - 1
            ) // self.page_size,
        )

        start = (page - 1) * self.page_size
        end = start + self.page_size

        results = []

        for match in matches[start:end]:
            verse = match.verse
            chapter = verse.chapter
            book = chapter.book

            results.append(
                {
                    "result_type": "verse",
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
                    "version": BibleVersionSerializer(
                        match.bible_version
                    ).data,
                }
            )

        reference_data = None

        if reference is not None:
            reference_data = {
                "book": BookSerializer(
                    reference["book"]
                ).data,
                "chapter": reference["chapter"],
                "verse": reference["verse"],
            }

        return Response(
            {
                "query": query,
                "mode": (
                    "all_versions"
                    if all_versions
                    else "single_version"
                ),
                "search_type": search_type,
                "reference": reference_data,
                "version": (
                    None
                    if version is None
                    else BibleVersionSerializer(
                        version
                    ).data
                ),
                "count": total_results,
                "page": page,
                "total_pages": total_pages,
                "results": results,
            }
        )

