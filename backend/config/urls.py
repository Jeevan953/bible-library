from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from bible.models import BibleVersion

# Simple home view
def home(request):
    return JsonResponse({
        'message': 'Bible Library API',
        'status': 'running',
        'total_versions': BibleVersion.objects.count(),
        'endpoints': {
            'admin': '/admin/',
            'api': '/api/',
            'versions': '/api/versions/',
            'verses': '/api/verses/',
        }
    })

# Simple versions list view (without DRF)
def version_list(request):
    versions = BibleVersion.objects.all().order_by('name')
    data = []
    for v in versions:
        data.append({
            'id': v.id,
            'abbreviation': v.abbreviation,
            'name': v.name,
            'language': v.language,
            'year': v.year,
        })
    return JsonResponse(data, safe=False)

# Main urlpatterns
urlpatterns = [
    path('', home, name='home'),
    path("api/", include("bible.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
