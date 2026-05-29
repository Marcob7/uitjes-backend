from django.utils import timezone
from rest_framework import serializers

from .models import Category, City, Event, Favorite, Feedback, NewsletterSignup, Tag


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
            "rating_value",
            "review_count",
            "rating_source",
            "rating_max",
            "rating_url",
            "rating_last_checked_at",
            "latitude",
            "longitude",
        ]


def normalize_api_value(value):
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.lower() in {"nan", "none", "null", "n/a", "na"}:
            return None
        return cleaned

    return value


class CityContentSerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    price_note = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()
    ticket_url = serializers.SerializerMethodField()
    reservation_url = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    def get_city(self, obj):
        if obj.city_id:
            return normalize_api_value(obj.city.slug)
        return None

    def get_category(self, obj):
        if obj.category_id:
            return normalize_api_value(obj.category.name)
        return None

    def get_image_url(self, obj):
        return normalize_api_value(obj.image_url)

    def get_venue(self, obj):
        if obj.venue_id:
            return normalize_api_value(obj.venue.name)
        return None

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

    def get_price_note(self, obj):
        return normalize_api_value(obj.price_note)

    def get_source_url(self, obj):
        return normalize_api_value(obj.source_url)

    def get_ticket_url(self, obj):
        return normalize_api_value(obj.ticket_url)

    def get_reservation_url(self, obj):
        return None

    def get_tags(self, obj):
        return [
            tag.slug
            for tag in obj.tags.all()
            if normalize_api_value(tag.slug) is not None
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in ("slug", "title", "kind", "summary", "rating_source", "rating_url"):
            data[field] = normalize_api_value(data.get(field))
        return data

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "title",
            "city",
            "kind",
            "category",
            "summary",
            "image_url",
            "venue",
            "latitude",
            "longitude",
            "price_note",
            "is_free",
            "start_at",
            "end_at",
            "source_url",
            "ticket_url",
            "reservation_url",
            "rating_value",
            "review_count",
            "rating_source",
            "rating_max",
            "rating_url",
            "rating_last_checked_at",
            "tags",
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


class NewsletterSignupSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True, allow_blank=False)
    preferred_city = serializers.CharField(required=False, allow_blank=True, max_length=120)
    city = serializers.CharField(
        source="preferred_city",
        required=False,
        allow_blank=True,
        max_length=120,
    )
    frequency = serializers.ChoiceField(
        choices=NewsletterSignup.Frequency.choices,
        required=False,
    )
    interests = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[(value, value) for value in sorted(NewsletterSignup.INTEREST_CHOICES)]
        ),
        required=False,
        allow_empty=True,
    )
    source = serializers.CharField(required=False, allow_blank=True, max_length=80)

    class Meta:
        model = NewsletterSignup
        fields = [
            "id",
            "email",
            "preferred_city",
            "city",
            "frequency",
            "interests",
            "source",
            "is_active",
            "created_at",
            "updated_at",
            "confirmed_at",
            "unsubscribed_at",
        ]
        read_only_fields = [
            "id",
            "is_active",
            "created_at",
            "updated_at",
            "confirmed_at",
            "unsubscribed_at",
        ]

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        preferred_city = attrs.get("preferred_city")
        if isinstance(preferred_city, str):
            attrs["preferred_city"] = preferred_city.strip()
        return attrs

    def validate_city(self, value):
        return value.strip()

    def validate_preferred_city(self, value):
        return value.strip()

    def validate_source(self, value):
        return value.strip()

    def validate_interests(self, value):
        return list(dict.fromkeys(value))


class FavoriteSerializer(serializers.ModelSerializer):
    event_id = serializers.IntegerField(source="event.id", read_only=True)
    title = serializers.CharField(source="event.title", read_only=True)
    slug = serializers.CharField(source="event.slug", read_only=True)
    city = serializers.CharField(source="event.city.slug", read_only=True)
    kind = serializers.CharField(source="event.kind", read_only=True)
    category = serializers.SerializerMethodField()
    summary = serializers.CharField(source="event.summary", read_only=True)
    image_url = serializers.URLField(source="event.image_url", read_only=True)

    def get_category(self, obj):
        if obj.event.category_id:
            return obj.event.category.name
        return None

    class Meta:
        model = Favorite
        fields = [
            "id",
            "event_id",
            "title",
            "slug",
            "city",
            "kind",
            "category",
            "summary",
            "image_url",
            "created_at",
        ]
