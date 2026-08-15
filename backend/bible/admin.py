from django.contrib import admin

from .models import HitchcockName


@admin.register(HitchcockName)
class HitchcockNameAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "source_id",
        "definition",
    )
    search_fields = ("name", "definition")
