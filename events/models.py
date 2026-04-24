from django.db import models
from django.conf import settings


class City(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    hero_image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Venue(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(blank=True, null=True, db_index=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="venues")
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    venue_type = models.CharField(max_length=50, blank=True, null=True)

    # Coordinaten van de vaste locatie, bijvoorbeeld een restaurant, theater of museum
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=32, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    class Facet(models.TextChoices):
        AUDIENCE = "audience", "Audience"
        MOMENT = "moment", "Moment"
        VIBE = "vibe", "Vibe"
        WEATHER = "weather", "Weather"
        FEATURE = "feature", "Feature"
        THEME = "theme", "Theme"

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    facet = models.CharField(max_length=20, choices=Facet.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["facet", "name"]

    def __str__(self):
        return f"{self.name} ({self.facet})"


class Event(models.Model):
    class Kind(models.TextChoices):
        EVENT = "event", "Event"
        ACTIVITY = "activity", "Activity"
        FESTIVAL = "festival", "Festival"
        PLACE = "place", "Place"
        FOOD_DRINK = "food_drink", "Food & Drink"

    class IndoorOutdoor(models.TextChoices):
        INDOOR = "indoor", "Binnen"
        OUTDOOR = "outdoor", "Buiten"
        BOTH = "both", "Binnen & buiten"

    class WeatherSuitability(models.TextChoices):
        ALL = "all", "All weather"
        SUN = "sun", "Good weather"
        RAIN = "rain", "Rain proof"

    title = models.CharField(max_length=255)
    slug = models.SlugField(blank=True, null=True, db_index=True)
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.EVENT,
    )
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="events")
    venue = models.ForeignKey(
        Venue,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="events")

    # Omschrijving van het event
    description = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    ticket_url = models.URLField(blank=True, null=True)

    # Optioneel specifiek adres voor dit event
    # Dit is handig als een event een andere locatie heeft dan de standaard venue
    address = models.CharField(max_length=255, blank=True, null=True)

    # Optionele event-specifieke coordinaten
    # Eerst gebruiken we deze, en als die leeg zijn vallen we later terug op de venue-coordinaten
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Niet elk item heeft een vaste datum
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    is_free = models.BooleanField(default=False)
    price_min = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    price_max = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    price_note = models.CharField(max_length=255, blank=True, null=True)

    # Voor imports/upserts:
    # - source_url: liefst unieke bron (event pagina)
    # - date_text: originele datumtekst (ook bij jaarrond/perioden)
    # - source: waar komt dit record vandaan
    # - dedupe_key: fallback unique key als er geen source_url is
    source_url = models.URLField(blank=True, null=True, db_index=True)
    date_text = models.CharField(max_length=255, blank=True, null=True)
    raw_date_text = models.CharField(max_length=255, blank=True, null=True)
    source = models.CharField(max_length=64, blank=True, null=True)
    dedupe_key = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    opening_hours_text = models.CharField(max_length=255, blank=True, null=True)
    indoor_outdoor = models.CharField(
        max_length=20,
        choices=IndoorOutdoor.choices,
        blank=True,
        null=True,
    )
    weather_suitability = models.CharField(
        max_length=20,
        choices=WeatherSuitability.choices,
        blank=True,
        null=True,
    )
    is_featured = models.BooleanField(default=False)
    is_hidden_gem = models.BooleanField(default=False)
    status_override = models.CharField(max_length=100, blank=True, null=True)
    editor_rating = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["city", "dedupe_key"],
                name="uniq_event_city_dedupe",
            ),
        ]

    def __str__(self):
        return self.title


class Feedback(models.Model):
    message = models.TextField()
    email = models.EmailField(blank=True)
    page_url = models.URLField(blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback #{self.id} ({self.created_at:%Y-%m-%d})"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event = models.ForeignKey("Event", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "event")
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        return f"{self.user_id} -> {self.event_id}"
