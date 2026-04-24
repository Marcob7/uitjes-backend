from django.db import migrations
from django.utils.text import slugify


BASE_CATEGORIES = [
    ("Cultuur", "cultuur", "event"),
    ("Muziek", "muziek", "event"),
    ("Festival", "festival", "festival"),
    ("Eten & drinken", "eten-drinken", "food_drink"),
    ("Met kinderen", "met-kinderen", "activity"),
    ("Binnen", "binnen", "place"),
    ("Buiten", "buiten", "place"),
    ("Activiteit", "activiteit", "activity"),
]

BASE_TAGS = [
    ("Solo", "solo", "audience"),
    ("Date", "date", "audience"),
    ("Gezin", "gezin", "audience"),
    ("Vrienden", "vrienden", "audience"),
    ("Nu", "nu", "moment"),
    ("Vanavond", "vanavond", "moment"),
    ("Morgen", "morgen", "moment"),
    ("Weekend", "weekend", "moment"),
    ("Cultureel", "cultureel", "vibe"),
    ("Actief", "actief", "vibe"),
    ("Eten & drinken", "eten-drinken", "vibe"),
    ("Relaxed", "relaxed", "vibe"),
    ("Goed weer", "goed-weer", "weather"),
    ("Slecht weer", "slecht-weer", "weather"),
    ("Featured", "featured", "feature"),
    ("Hidden gem", "hidden-gem", "feature"),
]


def unique_slug(base, used_values, fallback):
    base_value = slugify(base or "") or fallback
    candidate = base_value
    counter = 2
    while candidate in used_values:
        candidate = f"{base_value}-{counter}"
        counter += 1
    used_values.add(candidate)
    return candidate


def seed_and_backfill(apps, schema_editor):
    City = apps.get_model("events", "City")
    Venue = apps.get_model("events", "Venue")
    Event = apps.get_model("events", "Event")
    Category = apps.get_model("events", "Category")
    Tag = apps.get_model("events", "Tag")

    for name, slug, kind in BASE_CATEGORIES:
        Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": kind,
                "is_active": True,
            },
        )

    for name, slug, facet in BASE_TAGS:
        Tag.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "facet": facet,
                "is_active": True,
            },
        )

    for city in City.objects.all():
        if not city.slug:
            city.slug = unique_slug(city.name, set(City.objects.exclude(pk=city.pk).values_list("slug", flat=True)), f"city-{city.pk}")
            city.save(update_fields=["slug"])

    for venue in Venue.objects.select_related("city").all():
        changed_fields = []
        if not venue.slug:
            base_slug = f"{venue.name}-{venue.city.slug}" if venue.city_id else venue.name
            venue.slug = slugify(base_slug) or f"venue-{venue.pk}"
            changed_fields.append("slug")
        if changed_fields:
            venue.save(update_fields=changed_fields)

    used_event_slugs = set(
        Event.objects.exclude(slug__isnull=True)
        .exclude(slug__exact="")
        .values_list("slug", flat=True)
    )

    for event in Event.objects.select_related("city").all():
        changed_fields = []
        if not event.raw_date_text and event.date_text:
            event.raw_date_text = event.date_text
            changed_fields.append("raw_date_text")

        if not event.slug:
            city_slug = event.city.slug if event.city_id else "event"
            event.slug = unique_slug(
                f"{event.title}-{city_slug}",
                used_event_slugs,
                f"event-{event.pk}",
            )
            changed_fields.append("slug")

        if changed_fields:
            event.save(update_fields=changed_fields)


def rollback_seed(apps, schema_editor):
    # Leave backfilled slugs/raw_date_text in place on rollback to avoid destructive behavior.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0007_phase1_backend_expansion"),
    ]

    operations = [
        migrations.RunPython(seed_and_backfill, rollback_seed),
    ]
