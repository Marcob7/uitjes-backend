import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import make_aware
from django.utils.text import slugify

from events.models import Category, City, Event, Tag, Venue

DUTCH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


def norm(value):
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def slug_simple(value):
    normalized = norm(value).lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "-", normalized).strip("-")
    return normalized


def first_value(row, *columns):
    for column in columns:
        value = norm(row.get(column))
        if value:
            return value
    return ""


def parse_bool(value):
    normalized = norm(value).lower()
    if not normalized:
        return None
    return normalized in {"1", "true", "yes", "ja", "y"}


def parse_decimal(value):
    normalized = norm(value)
    if not normalized:
        return None

    normalized = normalized.replace("€", "").replace("eur", "").replace(",", ".")
    normalized = normalized.strip()

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def parse_tag_values(value):
    raw = norm(value)
    if not raw:
        return []
    parts = re.split(r"[;,|]", raw)
    return [part.strip() for part in parts if part.strip()]


def parse_numeric_date(raw):
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", raw)
    if not match:
        return None

    day, month, year = map(int, match.groups())
    return make_aware(datetime(year, month, day, 9, 0, 0))


def parse_written_single_date(raw):
    match = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", raw)
    if not match:
        return None

    day = int(match.group(1))
    month = DUTCH_MONTHS.get(match.group(2))
    year = int(match.group(3))

    if not month:
        return None

    return make_aware(datetime(year, month, day, 9, 0, 0))


def parse_written_same_month_range(raw):
    match = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", raw)
    if not match:
        return (None, None)

    start_day = int(match.group(1))
    end_day = int(match.group(2))
    month = DUTCH_MONTHS.get(match.group(3))
    year = int(match.group(4))

    if not month:
        return (None, None)

    start_at = make_aware(datetime(year, month, start_day, 9, 0, 0))
    end_at = make_aware(datetime(year, month, end_day, 17, 0, 0))
    return (start_at, end_at)


def parse_written_cross_month_range(raw):
    match = re.search(
        r"\b(\d{1,2})\s+([a-z]+)\s*-\s*(\d{1,2})\s+([a-z]+)\s+(\d{4})\b",
        raw,
    )
    if not match:
        return (None, None)

    start_day = int(match.group(1))
    start_month = DUTCH_MONTHS.get(match.group(2))
    end_day = int(match.group(3))
    end_month = DUTCH_MONTHS.get(match.group(4))
    year = int(match.group(5))

    if not start_month or not end_month:
        return (None, None)

    start_at = make_aware(datetime(year, start_month, start_day, 9, 0, 0))
    end_at = make_aware(datetime(year, end_month, end_day, 17, 0, 0))
    return (start_at, end_at)


def parse_date_range(raw_text):
    raw = norm(raw_text).lower()
    if not raw:
        return (None, None)

    raw = raw.replace("â€“", "-").replace("â€”", "-").replace("–", "-").replace("—", "-")
    raw = raw.replace("t/m", "-").replace("tot en met", "-")

    if any(keyword in raw for keyword in ["jaarrond", "gehele jaar", "dagelijks", "elke ", "maart-oktober", "april-november", "maart-december", "april-december"]):
        return (None, None)

    start_at, end_at = parse_written_cross_month_range(raw)
    if start_at or end_at:
        return (start_at, end_at)

    start_at, end_at = parse_written_same_month_range(raw)
    if start_at or end_at:
        return (start_at, end_at)

    single = parse_numeric_date(raw)
    if single:
        return (single, None)

    single = parse_written_single_date(raw)
    if single:
        return (single, None)

    return (None, None)


def build_dedupe_key(city_slug, title, raw_date_text, source_id=None):
    if source_id:
        return f"{city_slug}|source|{slug_simple(source_id)}"[:255]
    return f"{city_slug}|{slug_simple(title)}|{slug_simple(raw_date_text or '')}"[:255]


def infer_kind(explicit_kind, type_value, category_value):
    normalized = (explicit_kind or type_value or category_value or "").strip().lower()

    if normalized in {"festival", "festivals"}:
        return Event.Kind.FESTIVAL
    if normalized in {"activity", "activiteit", "uitje"}:
        return Event.Kind.ACTIVITY
    if normalized in {"place", "plek", "locatie"}:
        return Event.Kind.PLACE
    if normalized in {"food", "food_drink", "eten", "eten-drinken", "horeca"}:
        return Event.Kind.FOOD_DRINK
    return Event.Kind.EVENT


def infer_category_name(raw_category, type_value, kind_value):
    if raw_category:
        return raw_category

    normalized = (type_value or kind_value or "").strip().lower()
    if "festival" in normalized:
        return "Festival"
    if normalized in {"food", "food_drink", "eten", "eten-drinken", "horeca"}:
        return "Eten & drinken"
    if "kind" in normalized or "famil" in normalized:
        return "Met kinderen"
    return ""


def get_or_create_category(name, kind):
    category_name = norm(name)
    if not category_name:
        return None

    category_slug = slugify(category_name)
    category, _ = Category.objects.get_or_create(
        slug=category_slug,
        defaults={
            "name": category_name,
            "kind": kind,
            "is_active": True,
        },
    )

    updates = []
    if not category.kind and kind:
        category.kind = kind
        updates.append("kind")
    if updates:
        category.save(update_fields=updates)

    return category


def get_or_create_tag(name, facet):
    tag_name = norm(name)
    if not tag_name:
        return None

    tag_slug = slugify(tag_name)
    tag, _ = Tag.objects.get_or_create(
        slug=tag_slug,
        defaults={
            "name": tag_name,
            "facet": facet,
            "is_active": True,
        },
    )
    return tag


def get_or_create_venue(city, name, address="", postal_code="", website="", venue_type=""):
    venue_name = norm(name)
    if not venue_name:
        return None

    venue, _ = Venue.objects.get_or_create(
        city=city,
        name=venue_name,
        defaults={
            "slug": slugify(f"{venue_name}-{city.slug}") or None,
            "address": norm(address),
            "postal_code": norm(postal_code) or None,
            "website": norm(website) or None,
            "venue_type": norm(venue_type) or None,
        },
    )

    changed_fields = []
    if not venue.slug:
        venue.slug = slugify(f"{venue.name}-{city.slug}") or f"venue-{venue.pk}"
        changed_fields.append("slug")
    if not venue.address and norm(address):
        venue.address = norm(address)
        changed_fields.append("address")
    if not venue.postal_code and norm(postal_code):
        venue.postal_code = norm(postal_code)
        changed_fields.append("postal_code")
    if not venue.website and norm(website):
        venue.website = norm(website)
        changed_fields.append("website")
    if not venue.venue_type and norm(venue_type):
        venue.venue_type = norm(venue_type)
        changed_fields.append("venue_type")
    if changed_fields:
        venue.save(update_fields=changed_fields)

    return venue


class Command(BaseCommand):
    help = "Import events from Excel with safe upsert, enrichment fields and backwards-compatible column support."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Pad naar .xlsx")
        parser.add_argument("--city", required=True, help="City slug, bijvoorbeeld apeldoorn")
        parser.add_argument("--source", default="excel", help="Bronnaam, bijvoorbeeld excel_apeldoorn")

    @transaction.atomic
    def handle(self, *args, **opts):
        path = opts["file"]
        city_slug = norm(opts["city"]).lower()
        source = norm(opts["source"])
        name_map = {
            "apeldoorn": "Apeldoorn",
            "deventer": "Deventer",
            "zwolle": "Zwolle",
        }

        city, _ = City.objects.get_or_create(
            slug=city_slug,
            defaults={"name": name_map.get(city_slug, city_slug.title())},
        )

        df = pd.read_excel(path)
        df.columns = [norm(column) for column in df.columns]

        created = 0
        updated = 0
        skipped = 0
        errors = 0
        seen = set()

        for idx, row in df.iterrows():
            try:
                title = first_value(row, "Naam/Activiteit", "Title", "Naam")
                if not title:
                    skipped += 1
                    continue

                source_url = first_value(row, "Website", "SourceUrl") or None
                source_id = first_value(row, "SourceId", "BronId") or None
                raw_date_text = first_value(row, "DatumRaw", "Datum", "Datum/Periode") or None
                description = first_value(row, "Omschrijving", "Beschrijving", "Locatie/Omschrijving") or None
                summary = first_value(row, "Summary", "Samenvatting") or None
                type_value = first_value(row, "Type")
                kind_value = first_value(row, "Kind")
                category_value = first_value(row, "Category", "Categorie")
                venue_name = first_value(row, "Venue", "Locatie", "Locatie/Omschrijving")
                address = first_value(row, "Address", "Adres")
                postal_code = first_value(row, "PostalCode", "Postcode")
                website = first_value(row, "VenueWebsite")
                venue_type = first_value(row, "VenueType", "LocatieType")
                ticket_url = first_value(row, "TicketUrl", "Tickets")
                image_url = first_value(row, "ImageUrl", "Afbeelding")
                opening_hours_text = first_value(row, "OpeningHours", "Openingstijden")
                price_note = first_value(row, "PriceNote", "PrijsOpmerking")
                indoor_outdoor = first_value(row, "IndoorOutdoor", "BinnenBuiten").lower() or None
                weather_suitability = first_value(row, "WeatherSuitability", "WeerGeschikt").lower() or None
                status_override = first_value(row, "Status", "StatusOverride") or None
                price_min = parse_decimal(first_value(row, "PriceMin", "PrijsMin"))
                price_max = parse_decimal(first_value(row, "PriceMax", "PrijsMax"))
                editor_rating = parse_decimal(first_value(row, "Rating", "EditorRating"))
                latitude = parse_decimal(first_value(row, "Latitude", "Lat"))
                longitude = parse_decimal(first_value(row, "Longitude", "Lng", "Longitude"))
                is_free = parse_bool(first_value(row, "IsFree", "Gratis"))
                is_featured = parse_bool(first_value(row, "Featured", "Uitgelicht"))
                is_hidden_gem = parse_bool(first_value(row, "HiddenGem", "Hidden Gem"))

                kind = infer_kind(kind_value, type_value, category_value)
                category_name = infer_category_name(category_value, type_value, kind_value)
                category = get_or_create_category(category_name, kind) if category_name else None

                venue = get_or_create_venue(
                    city=city,
                    name=venue_name,
                    address=address,
                    postal_code=postal_code,
                    website=website,
                    venue_type=venue_type,
                )

                start_at = end_at = None
                explicit_start = first_value(row, "StartAt")
                explicit_end = first_value(row, "EndAt")

                if explicit_start:
                    start_at, _ = parse_date_range(explicit_start)
                if explicit_end:
                    end_at, _ = parse_date_range(explicit_end)
                if not start_at and raw_date_text:
                    start_at, end_at = parse_date_range(raw_date_text)

                dedupe_key = build_dedupe_key(city_slug, title, raw_date_text, source_id=source_id)
                internal_key = source_url or f"{city_slug}|{dedupe_key}"
                if internal_key in seen:
                    skipped += 1
                    continue
                seen.add(internal_key)

                defaults = {
                    "title": title,
                    "slug": slugify(f"{title}-{city.slug}") or None,
                    "kind": kind,
                    "city": city,
                    "venue": venue,
                    "category": category,
                    "description": description,
                    "summary": summary,
                    "address": norm(address) or None,
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_at": start_at,
                    "end_at": end_at,
                    "is_free": is_free if is_free is not None else False,
                    "price_min": price_min,
                    "price_max": price_max,
                    "price_note": price_note or None,
                    "source_url": source_url,
                    "ticket_url": ticket_url or None,
                    "image_url": image_url or None,
                    "date_text": raw_date_text,
                    "raw_date_text": raw_date_text,
                    "source": source,
                    "dedupe_key": dedupe_key if not source_url else None,
                    "opening_hours_text": opening_hours_text or None,
                    "indoor_outdoor": indoor_outdoor if indoor_outdoor in {"indoor", "outdoor", "both"} else None,
                    "weather_suitability": weather_suitability if weather_suitability in {"all", "sun", "rain"} else None,
                    "status_override": status_override or None,
                    "editor_rating": editor_rating,
                    "is_featured": bool(is_featured) if is_featured is not None else False,
                    "is_hidden_gem": bool(is_hidden_gem) if is_hidden_gem is not None else False,
                }

                if source_url:
                    event, was_created = Event.objects.update_or_create(
                        source_url=source_url,
                        defaults=defaults,
                    )
                else:
                    event, was_created = Event.objects.update_or_create(
                        city=city,
                        dedupe_key=dedupe_key,
                        defaults=defaults,
                    )

                tag_objects = []
                for audience_name in parse_tag_values(first_value(row, "AudienceTags", "Audiences")):
                    tag = get_or_create_tag(audience_name, Tag.Facet.AUDIENCE)
                    if tag:
                        tag_objects.append(tag)

                for moment_name in parse_tag_values(first_value(row, "MomentTags", "Moments")):
                    tag = get_or_create_tag(moment_name, Tag.Facet.MOMENT)
                    if tag:
                        tag_objects.append(tag)

                for vibe_name in parse_tag_values(first_value(row, "VibeTags", "Vibes")):
                    tag = get_or_create_tag(vibe_name, Tag.Facet.VIBE)
                    if tag:
                        tag_objects.append(tag)

                event.tags.set(tag_objects)

                if was_created:
                    created += 1
                else:
                    updated += 1

            except Exception as exc:
                errors += 1
                self.stderr.write(f"Row {idx + 2}: ERROR {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. rows={len(df)} unique={len(seen)} created={created} updated={updated} skipped={skipped} errors={errors}"
        ))
