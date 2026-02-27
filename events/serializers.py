from rest_framework import serializers
from .models import Event, Feedback, Favorite

class EventSerializer(serializers.ModelSerializer):
    # We sturen city terug als slug (string) i.p.v. een heel object
    city = serializers.CharField(source="city.slug")
    # Venue kan leeg zijn (null in DB), daarom allow_null
    venue = serializers.CharField(source="venue.name", allow_null=True)

    # Nieuw: doorlopend label + originele datumtekst
    is_ongoing = serializers.SerializerMethodField()

    def get_is_ongoing(self, obj):
        return obj.start_at is None

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "city",
            "venue",
            "start_at",
            "end_at",
            "date_text",     # <- nieuw
            "is_ongoing",    # <- nieuw
            "is_free",
            "price_min",
            "source_url",
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