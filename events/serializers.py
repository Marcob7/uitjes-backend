from rest_framework import serializers
from .models import Event, Feedback, Favorite


class EventSerializer(serializers.ModelSerializer):
    # We sturen city terug als slug-string
    city = serializers.CharField(source="city.slug")

    # Venue kan leeg zijn, daarom allow_null=True
    venue = serializers.CharField(source="venue.name", allow_null=True)
    venue_address = serializers.CharField(source="venue.address", allow_null=True)

    # Extra velden voor de frontend
    is_ongoing = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()

    def get_is_ongoing(self, obj):
        return obj.start_at is None

    def get_latitude(self, obj):
        # Gebruik eerst event-coordinaten
        if obj.latitude is not None:
            return float(obj.latitude)

        # Val anders terug op venue-coordinaten
        if obj.venue and obj.venue.latitude is not None:
            return float(obj.venue.latitude)

        return None

    def get_longitude(self, obj):
        # Gebruik eerst event-coordinaten
        if obj.longitude is not None:
            return float(obj.longitude)

        # Val anders terug op venue-coordinaten
        if obj.venue and obj.venue.longitude is not None:
            return float(obj.venue.longitude)

        return None

    def get_address(self, obj):
        # Gebruik eerst het event-adres
        if obj.address:
            return obj.address

        # Val anders terug op het venue-adres
        if obj.venue and obj.venue.address:
            return obj.venue.address

        return None

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "city",
            "venue",
            "venue_address",
            "address",
            "start_at",
            "end_at",
            "date_text",
            "is_ongoing",
            "is_free",
            "price_min",
            "source_url",
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