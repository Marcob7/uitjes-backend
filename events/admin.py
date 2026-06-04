from django.contrib import admin

from .models import Category, City, Event, Favorite, Feedback, NewsletterSignup, Tag, Venue


class HasImageUrlFilter(admin.SimpleListFilter):
    title = "image_url"
    parameter_name = "has_image_url"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Aanwezig"),
            ("no", "Ontbreekt"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(image_url__isnull=True).exclude(image_url__exact="")
        if self.value() == "no":
            return queryset.filter(image_url__isnull=True) | queryset.filter(image_url__exact="")
        return queryset


class HasCoordinatesFilter(admin.SimpleListFilter):
    title = "coordinaten"
    parameter_name = "has_coordinates"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Aanwezig"),
            ("no", "Ontbreekt"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(latitude__isnull=False, longitude__isnull=False)
        if self.value() == "no":
            return queryset.filter(latitude__isnull=True) | queryset.filter(longitude__isnull=True)
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "is_active", "event_count")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="events")
    def event_count(self, obj):
        return obj.events.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "facet", "is_active")
    list_filter = ("facet", "is_active")
    search_fields = ("name", "slug")
    ordering = ("facet", "name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "event_count", "venue_count")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="events")
    def event_count(self, obj):
        return obj.events.count()

    @admin.display(description="venues")
    def venue_count(self, obj):
        return obj.venues.count()


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "venue_type", "postal_code", "website")
    list_filter = ("city", "venue_type")
    search_fields = ("name", "slug", "address", "postal_code", "website")
    ordering = ("city__name", "name")
    autocomplete_fields = ("city",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    actions = (
        "mark_published",
        "mark_hidden",
        "mark_archived",
        "mark_needs_review",
        "mark_expired",
    )
    list_display = (
        "title",
        "status",
        "city",
        "kind",
        "category",
        "start_at",
        "end_at",
        "has_source_url",
        "has_image_url",
        "has_coordinates",
        "is_free",
        "is_featured",
        "is_hidden_gem",
    )
    list_filter = (
        "status",
        "city",
        "kind",
        "category",
        ("start_at", admin.DateFieldListFilter),
        ("end_at", admin.DateFieldListFilter),
        HasImageUrlFilter,
        HasCoordinatesFilter,
        "is_featured",
        "is_hidden_gem",
        "is_free",
        "indoor_outdoor",
        "weather_suitability",
    )
    search_fields = (
        "title",
        "slug",
        "city__name",
        "city__slug",
        "venue__name",
        "venue__slug",
        "address",
        "source_url",
        "summary",
        "description",
        "date_text",
        "raw_date_text",
    )
    ordering = ("city__name", "start_at", "title")
    list_select_related = ("city", "venue", "category")
    autocomplete_fields = ("city", "venue", "category")
    filter_horizontal = ("tags",)
    readonly_fields = ("updated_at", "source", "dedupe_key", "raw_date_text")
    fieldsets = (
        (
            "Basis",
            {
                "fields": (
                    "title",
                    "slug",
                    "kind",
                    "status",
                    "status_note",
                    "city",
                    "venue",
                    "category",
                    "tags",
                    "summary",
                    "description",
                )
            },
        ),
        (
            "Locatie",
            {
                "fields": (
                    "address",
                    "latitude",
                    "longitude",
                    "indoor_outdoor",
                    "weather_suitability",
                )
            },
        ),
        ("Datum/tijd", {"fields": ("start_at", "end_at", "date_text", "opening_hours_text")}),
        ("Bron/links", {"fields": ("source_url", "ticket_url")}),
        ("Media", {"fields": ("image_url",)}),
        (
            "Highlight/priority",
            {
                "fields": (
                    "is_featured",
                    "is_hidden_gem",
                    "status_override",
                    "editor_rating",
                    "rating_value",
                    "review_count",
                    "rating_source",
                    "rating_max",
                    "rating_url",
                    "rating_last_checked_at",
                )
            },
        ),
        (
            "Prijs",
            {"fields": ("is_free", "price_min", "price_max", "price_note")},
        ),
        (
            "Import/debug",
            {
                "classes": ("collapse",),
                "fields": ("source", "dedupe_key", "raw_date_text", "updated_at"),
            },
        ),
    )

    @admin.display(boolean=True, description="source_url")
    def has_source_url(self, obj):
        return bool(obj.source_url)

    @admin.display(boolean=True, description="image_url")
    def has_image_url(self, obj):
        return bool(obj.image_url)

    @admin.display(boolean=True, description="coords")
    def has_coordinates(self, obj):
        return obj.latitude is not None and obj.longitude is not None

    def _mark_status(self, request, queryset, lifecycle_status):
        updated = queryset.update(status=lifecycle_status)
        self.message_user(
            request,
            f"{updated} event(s) gemarkeerd als {lifecycle_status}.",
        )

    @admin.action(description="Markeer als published")
    def mark_published(self, request, queryset):
        self._mark_status(request, queryset, Event.Status.PUBLISHED)

    @admin.action(description="Markeer als hidden")
    def mark_hidden(self, request, queryset):
        self._mark_status(request, queryset, Event.Status.HIDDEN)

    @admin.action(description="Markeer als archived")
    def mark_archived(self, request, queryset):
        self._mark_status(request, queryset, Event.Status.ARCHIVED)

    @admin.action(description="Markeer als needs_review")
    def mark_needs_review(self, request, queryset):
        self._mark_status(request, queryset, Event.Status.NEEDS_REVIEW)

    @admin.action(description="Markeer als expired")
    def mark_expired(self, request, queryset):
        self._mark_status(request, queryset, Event.Status.EXPIRED)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "event_title", "city", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "event__title",
        "event__slug",
    )
    list_filter = ("event__city", "created_at")
    ordering = ("-created_at",)
    list_select_related = ("user", "event", "event__city")
    autocomplete_fields = ("user", "event")

    @admin.display(description="event")
    def event_title(self, obj):
        return obj.event.title

    @admin.display(description="city")
    def city(self, obj):
        return obj.event.city


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "email", "short_message", "page_url")
    search_fields = ("message", "email", "page_url")
    list_filter = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description="message")
    def short_message(self, obj):
        return obj.message[:60] + ("..." if len(obj.message) > 60 else "")


@admin.register(NewsletterSignup)
class NewsletterSignupAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "preferred_city",
        "frequency",
        "interests",
        "source",
        "is_active",
        "created_at",
        "updated_at",
        "confirmed_at",
        "unsubscribed_at",
    )
    list_filter = (
        "frequency",
        "is_active",
        "source",
        "preferred_city",
        "created_at",
    )
    search_fields = ("email", "preferred_city")
    readonly_fields = (
        "created_at",
        "updated_at",
        "confirmed_at",
        "unsubscribed_at",
        "ip_address",
        "user_agent",
    )
    ordering = ("-created_at",)
