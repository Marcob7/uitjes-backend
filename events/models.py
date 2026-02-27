from django.db import models
from django.conf import settings


class City(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Venue(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="venues")
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class Event(models.Model):
    title = models.CharField(max_length=255)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="events")
    venue = models.ForeignKey(
        Venue,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    # Nieuw: omschrijving uit Excel kunnen opslaan
    description = models.TextField(blank=True, null=True)

    # Belangrijk: niet elk item heeft een vaste datum (jaarrond, april–november, etc.)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    is_free = models.BooleanField(default=False)
    price_min = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Voor imports/upserts:
    # - source_url: liefst unieke bron (event pagina)
    # - date_text: originele datumtekst (ook bij jaarrond/perioden)
    # - source: waar komt dit record vandaan (excel_apeldoorn / excel_deventer)
    # - dedupe_key: fallback unique key als er geen source_url is
    source_url = models.URLField(blank=True, null=True, db_index=True)
    date_text = models.CharField(max_length=255, blank=True, null=True)
    source = models.CharField(max_length=64, blank=True, null=True)
    dedupe_key = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Fallback dedupe: binnen dezelfde stad mag dedupe_key maar 1x voorkomen.
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