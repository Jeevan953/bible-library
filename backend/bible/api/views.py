from rest_framework import viewsets, generics
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework import filters
from django.db.models import Q
from bible.models import BibleVersion, VerseText, Book, Chapter
from bible.api.serializers import (
    BibleVersionSerializer, 
    VerseTextSerializer,
    BookSerializer,
    ChapterSerializer
)

@api_view(['GET'])
def api_root(request, format=None):
    """API Root endpoint"""
    return Response({
        'name': 'Bible Library API',
        'version': '1.0.0',
        'description': 'A digital Bible library with multiple translations',
        'endpoints': {
            'versions': reverse('version-list', request=request, format=format),
            'verses': reverse('verse-list', request=request, format=format),
            'books': reverse('book-list', request=request, format=format),
            'chapters': reverse('chapter-list', request=request, format=format),
            'search': '/api/search/',
            'parallel': '/api/parallel/',
        },
        'stats': {
            'total_versions': BibleVersion.objects.count(),
            'total_verses': VerseText.objects.count(),
            'total_books': Book.objects.count(),
            'total_chapters': Chapter.objects.count(),
        },
        'status': 'online',
    })

class BibleVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Bible versions"""
    queryset = BibleVersion.objects.all().order_by('name')
    serializer_class = BibleVersionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'abbreviation', 'language']
    ordering_fields = ['name', 'year', 'abbreviation']
    
    @action(detail=True, methods=['get'])
    def verses(self, request, pk=None):
        """Get all verses for a specific version"""
        version = self.get_object()
        book = request.query_params.get('book')
        chapter = request.query_params.get('chapter')
        
        queryset = VerseText.objects.filter(bible_version=version)
        
        if book:
            queryset = queryset.filter(verse__chapter__book__name__iexact=book)
        if chapter:
            queryset = queryset.filter(verse__chapter__number=chapter)
            
        queryset = queryset.select_related(
            'bible_version', 
            'verse__chapter__book'
        ).order_by('verse__chapter__book__position', 'verse__chapter__number', 'verse__number')
        
        serializer = VerseTextSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def books(self, request, pk=None):
        """Get all books for a specific version"""
        version = self.get_object()
        # Get books that have verses in this version
        books = Book.objects.filter(
            chapters__verses__versetext__bible_version=version
        ).distinct().order_by('position')
        
        serializer = BookSerializer(books, many=True)
        return Response(serializer.data)

class VerseTextViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for verse texts"""
    queryset = VerseText.objects.all().select_related(
        'bible_version', 
        'verse__chapter__book'
    )
    serializer_class = VerseTextSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['text']
    ordering_fields = ['verse__chapter__book__position', 'verse__chapter__number', 'verse__number']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by version
        version = self.request.query_params.get('version')
        if version:
            queryset = queryset.filter(bible_version__abbreviation__iexact=version)
        
        # Filter by book
        book = self.request.query_params.get('book')
        if book:
            queryset = queryset.filter(verse__chapter__book__name__iexact=book)
        
        # Filter by chapter
        chapter = self.request.query_params.get('chapter')
        if chapter:
            queryset = queryset.filter(verse__chapter__number=chapter)
        
        # Filter by verse range
        from_verse = self.request.query_params.get('from_verse')
        to_verse = self.request.query_params.get('to_verse')
        if from_verse and to_verse:
            queryset = queryset.filter(verse__number__gte=from_verse, verse__number__lte=to_verse)
        
        return queryset

class BookViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for books"""
    queryset = Book.objects.all().order_by('position')
    serializer_class = BookSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'slug']

class ChapterViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for chapters"""
    queryset = Chapter.objects.all().select_related('book')
    serializer_class = ChapterSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        book = self.request.query_params.get('book')
        if book:
            queryset = queryset.filter(book__name__iexact=book)
        return queryset

@api_view(['GET'])
def search_verses(request):
    """Search for verses across versions"""
    query = request.query_params.get('q', '')
    version = request.query_params.get('version')
    limit = int(request.query_params.get('limit', 50))
    
    if not query:
        return Response({'error': 'Search query required'}, status=400)
    
    queryset = VerseText.objects.select_related(
        'bible_version', 
        'verse__chapter__book'
    )
    
    if version:
        queryset = queryset.filter(bible_version__abbreviation__iexact=version)
    
    # Simple search (can be enhanced with full-text search)
    queryset = queryset.filter(text__icontains=query)[:limit]
    
    serializer = VerseTextSerializer(queryset, many=True)
    return Response({
        'query': query,
        'results': serializer.data,
        'count': len(serializer.data),
        'version_filter': version or 'all'
    })

@api_view(['GET'])
def parallel_verses(request):
    """Get parallel verses from multiple versions"""
    versions = request.query_params.getlist('versions')
    book = request.query_params.get('book')
    chapter = request.query_params.get('chapter')
    verse = request.query_params.get('verse')
    
    if not versions or not book or not chapter:
        return Response({'error': 'versions, book, and chapter required'}, status=400)
    
    results = {}
    for version_abbr in versions:
        queryset = VerseText.objects.filter(
            bible_version__abbreviation__iexact=version_abbr,
            verse__chapter__book__name__iexact=book,
            verse__chapter__number=chapter
        )
        if verse:
            queryset = queryset.filter(verse__number=verse)
        
        serializer = VerseTextSerializer(queryset, many=True)
        results[version_abbr] = serializer.data
    
    return Response({
        'book': book,
        'chapter': chapter,
        'verse': verse or 'all',
        'versions': results
    })