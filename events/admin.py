from django.contrib import admin

from .models import Category, City, Event, Feedback, Tag, Venue


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "facet", "is_active")
    list_filter = ("facet", "is_active")
    search_fields = ("name", "slug")
    ordering = ("facet", "name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "venue_type", "postal_code", "website")
    list_filter = ("city", "venue_type")
    search_fields = ("name", "slug", "address", "postal_code", "website")
    ordering = ("city__name", "name")
    autocomplete_fields = ("city",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "city",
        "kind",
        "category",
        "start_at",
        "is_free",
        "is_featured",
        "is_hidden_gem",
    )
    list_filter = (
        "city",
        "kind",
        "category",
        "is_free",
        "is_featured",
        "is_hidden_gem",
        "indoor_outdoor",
        "weather_suitability",
    )
    search_fields = (
        "title",
        "slug",
        "summary",
        "description",
        "date_text",
        "raw_date_text",
        "source_url",
        "address",
        "venue__name",
    )
    ordering = ("city__name", "start_at", "title")
    autocomplete_fields = ("city", "venue", "category")
    filter_horizontal = ("tags",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "email", "short_message", "page_url")
    search_fields = ("message", "email", "page_url")
    list_filter = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description="message")
    def short_message(self, obj):
        return obj.message[:60] + ("..." if len(obj.message) > 60 else "")
