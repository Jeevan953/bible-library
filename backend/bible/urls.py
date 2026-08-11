from django.urls import path

from .views import (
    BibleSearchAPIView,
    BibleVersionBookListAPIView,
    BibleVersionChapterListAPIView,
    BibleVersionListAPIView,
    ChapterReaderAPIView,
    ParallelChapterAPIView,
)

app_name = "bible"

urlpatterns = [
    path(
        "versions/",
        BibleVersionListAPIView.as_view(),
        name="version-list",
    ),
    path(
        "search/",
        BibleSearchAPIView.as_view(),
        name="bible-search",
    ),
    path(
        "versions/<str:abbreviation>/books/",
        BibleVersionBookListAPIView.as_view(),
        name="version-book-list",
    ),
    path(
        "versions/<str:abbreviation>/books/"
        "<int:book_position>/chapters/",
        BibleVersionChapterListAPIView.as_view(),
        name="version-chapter-list",
    ),
    path(
        "read/<str:abbreviation>/"
        "<int:book_position>/<int:chapter_number>/",
        ChapterReaderAPIView.as_view(),
        name="chapter-reader",
    ),
    path(
        "parallel/<int:book_position>/"
        "<int:chapter_number>/",
        ParallelChapterAPIView.as_view(),
        name="parallel-chapter",
    ),
]
