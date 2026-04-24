from django.utils import timezone
from rest_framework import serializers

from .models import Category, City, Event, Favorite, Feedback, Tag


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "hero_image_url",
            "is_active",
        ]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "kind", "is_active"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug", "facet", "is_active"]


class EventSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.slug")
    city_name = serializers.CharField(source="city.name", read_only=True)
    venue = serializers.CharField(source="venue.name", allow_null=True)
    venue_slug = serializers.CharField(source="venue.slug", allow_null=True, read_only=True)
    venue_address = serializers.CharField(source="venue.address", allow_null=True)
    category = serializers.CharField(source="category.slug", allow_null=True)
    category_label = serializers.SerializerMethodField()
    tags = TagSerializer(many=True, read_only=True)
    is_ongoing = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    audiences = serializers.SerializerMethodField()
    moments = serializers.SerializerMethodField()
    vibes = serializers.SerializerMethodField()

    def _tags_by_facet(self, obj, facet):
        return [tag.slug for tag in obj.tags.all() if tag.facet == facet]

    def get_category_label(self, obj):
        if obj.category:
            return obj.category.name
        return None

    def get_is_ongoing(self, obj):
        if obj.start_at is None or obj.end_at is None:
            return False

        now = timezone.now()
        return obj.start_at <= now <= obj.end_at

    def get_latitude(self, obj):
        if obj.latitude is not None:
            return float(obj.latitude)
        if obj.venue and obj.venue.latitude is not None:
            return float(obj.venue.latitude)
        return None

    def get_longitude(self, obj):
        if obj.longitude is not None:
            return float(obj.longitude)
        if obj.venue and obj.venue.longitude is not None:
            return float(obj.venue.longitude)
        return None

    def get_address(self, obj):
        if obj.address:
            return obj.address
        if obj.venue and obj.venue.address:
            return obj.venue.address
        return None

    def get_status(self, obj):
        if obj.status_override:
            return obj.status_override

        if self.get_is_ongoing(obj):
            return "Nu bezig"

        if obj.raw_date_text:
            return obj.raw_date_text

        if obj.date_text:
            return obj.date_text

        return "Datum nog te controleren"

    def get_audiences(self, obj):
        return self._tags_by_facet(obj, Tag.Facet.AUDIENCE)

    def get_moments(self, obj):
        return self._tags_by_facet(obj, Tag.Facet.MOMENT)

    def get_vibes(self, obj):
        return self._tags_by_facet(obj, Tag.Facet.VIBE)

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "kind",
            "title",
            "summary",
            "description",
            "city",
            "city_name",
            "venue",
            "venue_slug",
            "venue_address",
            "address",
            "category",
            "category_label",
            "tags",
            "audiences",
            "moments",
            "vibes",
            "start_at",
            "end_at",
            "date_text",
            "raw_date_text",
            "opening_hours_text",
            "is_ongoing",
            "is_free",
            "price_min",
            "price_max",
            "price_note",
            "source_url",
            "ticket_url",
            "image_url",
            "indoor_outdoor",
            "weather_suitability",
            "is_featured",
            "is_hidden_gem",
            "status",
            "editor_rating",
            "latitude",
            "longitude",
        ]


class FeedbackSerializer(serializers.ModelSerializer):
    message = serializers.CharField(
        allow_blank=False,
        min_length=10,
        help_text="Feedback bericht (minimaal 10 tekens)."
    )

    email = serializers.EmailField(required=False, allow_blank=True)
    page_url = serializers.URLField(required=False, allow_blank=True)

    class Meta:
        model = Feedback
        fields = ["id", "message", "email", "page_url", "created_at"]
        read_only_fields = ["id", "created_at"]


class FavoriteSerializer(serializers.ModelSerializer):
    event_id = serializers.IntegerField(source="event.id", read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "event_id", "created_at"]
