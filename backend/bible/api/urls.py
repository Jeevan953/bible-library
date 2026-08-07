# bible/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from bible.api.views import (
    api_root,
    BibleVersionViewSet, 
    VerseTextViewSet,
    BookViewSet,
    ChapterViewSet,
    search_verses,
    parallel_verses
)

# Create router
router = DefaultRouter()
router.register(r'versions', BibleVersionViewSet, basename='version')
router.register(r'verses', VerseTextViewSet, basename='verse')
router.register(r'books', BookViewSet, basename='book')
router.register(r'chapters', ChapterViewSet, basename='chapter')

# Custom API routes
urlpatterns = [
    path('', api_root, name='api-root'),
    path('', include(router.urls)),
    path('search/', search_verses, name='search-verses'),
    path('parallel/', parallel_verses, name='parallel-verses'),
]