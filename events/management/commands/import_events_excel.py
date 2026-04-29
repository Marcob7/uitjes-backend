import csv
import os
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


def is_known_bool(value):
    normalized = norm(value).lower()
    if not normalized:
        return True
    return normalized in {"1", "0", "true", "false", "yes", "no", "ja", "nee", "y", "n"}


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

    try:
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
    except ValueError:
        return (None, None)

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


def is_known_kind(explicit_kind, type_value):
    normalized = (explicit_kind or type_value or "").strip().lower()
    if not normalized:
        return True
    return normalized in {
        "festival",
        "festivals",
        "activity",
        "activiteit",
        "uitje",
        "place",
        "plek",
        "locatie",
        "food",
        "food_drink",
        "eten",
        "eten-drinken",
        "horeca",
        "event",
        "evenement",
    }


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


def get_missing_recommended_fields(
    title,
    city_slug,
    category_name,
    summary,
    image_url,
    venue_name,
    address,
    start_at,
    raw_date_text,
):
    missing_fields = []

    if not norm(title):
        missing_fields.append("title")
    if not norm(city_slug):
        missing_fields.append("city")
    if not norm(category_name):
        missing_fields.append("category")
    if not norm(summary):
        missing_fields.append("summary")
    if not norm(image_url):
        missing_fields.append("image_url")
    if not norm(venue_name) and not norm(address):
        missing_fields.append("venue_or_address")
    if not start_at and not norm(raw_date_text):
        missing_fields.append("date")

    return missing_fields


def make_report_row(
    row_number,
    action,
    title,
    city_slug,
    source_id,
    dedupe_key,
    warnings=None,
    errors=None,
    missing_recommended_fields=None,
    discover_ready=False,
    event_id="",
):
    return {
        "row_number": row_number,
        "action": action,
        "event_id": event_id or "",
        "title": title or "",
        "city": city_slug or "",
        "source_id": source_id or "",
        "dedupe_key": dedupe_key or "",
        "warnings": "; ".join(warnings or []),
        "errors": "; ".join(errors or []),
        "missing_recommended_fields": "; ".join(missing_recommended_fields or []),
        "discover_ready": "true" if discover_ready else "false",
    }


def write_report_file(path, report_rows):
    report_dir = os.path.dirname(path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)

    fieldnames = [
        "row_number",
        "action",
        "event_id",
        "title",
        "city",
        "source_id",
        "dedupe_key",
        "warnings",
        "errors",
        "missing_recommended_fields",
        "discover_ready",
    ]
    with open(path, "w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)


class Command(BaseCommand):
    help = "Import events from Excel with safe upsert, enrichment fields and backwards-compatible column support."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Pad naar .xlsx")
        parser.add_argument("--city", required=True, help="City slug, bijvoorbeeld apeldoorn")
        parser.add_argument("--source", default="excel", help="Bronnaam, bijvoorbeeld excel_apeldoorn")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lees en valideer het Excelbestand zonder database-wijzigingen.",
        )
        parser.add_argument(
            "--report-file",
            default="",
            help="Optioneel pad voor een CSV-importrapport.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        path = opts["file"]
        city_slug = norm(opts["city"]).lower()
        source = norm(opts["source"])
        dry_run = opts["dry_run"]
        report_file = norm(opts["report_file"])
        name_map = {
            "apeldoorn": "Apeldoorn",
            "deventer": "Deventer",
            "zwolle": "Zwolle",
        }

        if dry_run:
            city = City(slug=city_slug, name=name_map.get(city_slug, city_slug.title()))
            existing_city = City.objects.filter(slug=city_slug).first()
            if existing_city:
                city = existing_city
        else:
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
        warnings = 0
        seen = set()
        seen_source_ids = set()
        seen_dedupe_keys = set()
        duplicate_keys = set()
        bool_columns = [
            ("IsFree", "Gratis"),
            ("Featured", "Uitgelicht"),
            ("HiddenGem", "Hidden Gem"),
        ]
        report_rows = []

        for idx, row in df.iterrows():
            row_number = idx + 2
            try:
                title = first_value(row, "Naam/Activiteit", "Title", "Naam")
                source_id = first_value(row, "SourceId", "BronId") or None
                raw_date_text = first_value(row, "DatumRaw", "Datum", "Datum/Periode") or None
                if not title:
                    skipped += 1
                    warnings += 1
                    row_warnings = ["missing required field title"]
                    self.stdout.write(f"Row {row_number}: SKIP missing required field title")
                    report_rows.append(make_report_row(
                        row_number=row_number,
                        action="would_skip" if dry_run else "skipped",
                        title=title,
                        city_slug=city_slug,
                        source_id=source_id,
                        dedupe_key="",
                        warnings=row_warnings,
                        missing_recommended_fields=["title"],
                        discover_ready=False,
                    ))
                    continue

                source_url = first_value(row, "Website", "SourceUrl") or None
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
                row_warnings = []

                kind = infer_kind(kind_value, type_value, category_value)
                category_name = infer_category_name(category_value, type_value, kind_value)
                if not is_known_kind(kind_value, type_value):
                    row_warnings.append(f"unknown Kind value '{kind_value or type_value or category_value}'")
                if indoor_outdoor and indoor_outdoor not in {"indoor", "outdoor", "both"}:
                    row_warnings.append(f"unknown IndoorOutdoor value '{indoor_outdoor}'")
                if weather_suitability and weather_suitability not in {"all", "sun", "rain"}:
                    row_warnings.append(f"unknown WeatherSuitability value '{weather_suitability}'")
                for columns in bool_columns:
                    raw_bool = first_value(row, *columns)
                    if not is_known_bool(raw_bool):
                        row_warnings.append(f"unknown boolean value '{raw_bool}' in {columns[0]}")
                raw_latitude = first_value(row, "Latitude", "Lat")
                raw_longitude = first_value(row, "Longitude", "Lng", "Longitude")
                if raw_latitude and latitude is None:
                    row_warnings.append(f"invalid latitude '{raw_latitude}'")
                if raw_longitude and longitude is None:
                    row_warnings.append(f"invalid longitude '{raw_longitude}'")

                start_at = end_at = None
                explicit_start = first_value(row, "StartAt")
                explicit_end = first_value(row, "EndAt")

                if explicit_start:
                    start_at, _ = parse_date_range(explicit_start)
                if explicit_end:
                    end_at, _ = parse_date_range(explicit_end)
                if not start_at and raw_date_text:
                    start_at, end_at = parse_date_range(raw_date_text)
                if (explicit_start and not start_at) or (raw_date_text and not start_at and not end_at):
                    row_warnings.append(f"invalid date '{explicit_start or raw_date_text}'")

                dedupe_key = build_dedupe_key(city_slug, title, raw_date_text, source_id=source_id)
                missing_recommended_fields = get_missing_recommended_fields(
                    title=title,
                    city_slug=city_slug,
                    category_name=category_name,
                    summary=summary,
                    image_url=image_url,
                    venue_name=venue_name,
                    address=address,
                    start_at=start_at,
                    raw_date_text=raw_date_text,
                )
                discover_ready = not missing_recommended_fields
                internal_key = source_url or f"{city_slug}|{dedupe_key}"
                source_id_key = slug_simple(source_id) if source_id else ""
                file_dedupe_key = f"{city_slug}|{dedupe_key}"
                is_duplicate_source_id = bool(source_id_key and source_id_key in seen_source_ids)
                is_duplicate_dedupe_key = file_dedupe_key in seen_dedupe_keys

                if internal_key in seen:
                    skipped += 1
                    warnings += 1
                    duplicate_keys.add(internal_key)
                    row_warnings = [f"duplicate SourceId or dedupe_key '{internal_key}'"]
                    self.stdout.write(f"Row {row_number}: SKIP duplicate SourceId or dedupe_key '{internal_key}'")
                    report_rows.append(make_report_row(
                        row_number=row_number,
                        action="would_skip" if dry_run else "skipped",
                        title=title,
                        city_slug=city_slug,
                        source_id=source_id,
                        dedupe_key=dedupe_key,
                        warnings=row_warnings,
                        missing_recommended_fields=missing_recommended_fields,
                        discover_ready=discover_ready,
                    ))
                    continue
                if is_duplicate_source_id or is_duplicate_dedupe_key:
                    skipped += 1
                    warnings += 1
                    duplicate_value = source_id_key if is_duplicate_source_id else file_dedupe_key
                    duplicate_keys.add(duplicate_value)
                    row_warnings = [f"duplicate SourceId or dedupe_key '{duplicate_value}'"]
                    self.stdout.write(f"Row {row_number}: SKIP duplicate SourceId or dedupe_key '{duplicate_value}'")
                    report_rows.append(make_report_row(
                        row_number=row_number,
                        action="would_skip" if dry_run else "skipped",
                        title=title,
                        city_slug=city_slug,
                        source_id=source_id,
                        dedupe_key=dedupe_key,
                        warnings=row_warnings,
                        missing_recommended_fields=missing_recommended_fields,
                        discover_ready=discover_ready,
                    ))
                    continue

                seen.add(internal_key)
                if source_id_key:
                    seen_source_ids.add(source_id_key)
                seen_dedupe_keys.add(file_dedupe_key)

                if dry_run and row_warnings:
                    warnings += len(row_warnings)
                    for warning in row_warnings:
                        self.stdout.write(f"Row {row_number}: WARNING {warning}")

                if dry_run:
                    existing_event = (
                        Event.objects.filter(source_url=source_url).first()
                        if source_url
                        else Event.objects.filter(city__slug=city_slug, dedupe_key=dedupe_key).first()
                    )
                    if existing_event:
                        updated += 1
                        self.stdout.write(f"Row {row_number}: WOULD_UPDATE {title}")
                        report_rows.append(make_report_row(
                            row_number=row_number,
                            action="would_update",
                            event_id=existing_event.id,
                            title=title,
                            city_slug=city_slug,
                            source_id=source_id,
                            dedupe_key=dedupe_key,
                            warnings=row_warnings,
                            missing_recommended_fields=missing_recommended_fields,
                            discover_ready=discover_ready,
                        ))
                    else:
                        created += 1
                        self.stdout.write(f"Row {row_number}: WOULD_CREATE {title}")
                        report_rows.append(make_report_row(
                            row_number=row_number,
                            action="would_create",
                            title=title,
                            city_slug=city_slug,
                            source_id=source_id,
                            dedupe_key=dedupe_key,
                            warnings=row_warnings,
                            missing_recommended_fields=missing_recommended_fields,
                            discover_ready=discover_ready,
                        ))
                    continue

                category = get_or_create_category(category_name, kind) if category_name else None

                venue = get_or_create_venue(
                    city=city,
                    name=venue_name,
                    address=address,
                    postal_code=postal_code,
                    website=website,
                    venue_type=venue_type,
                )

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
                    action = "created"
                else:
                    updated += 1
                    action = "updated"

                report_rows.append(make_report_row(
                    row_number=row_number,
                    action=action,
                    event_id=event.id,
                    title=title,
                    city_slug=city_slug,
                    source_id=source_id,
                    dedupe_key=dedupe_key,
                    warnings=row_warnings,
                    missing_recommended_fields=missing_recommended_fields,
                    discover_ready=discover_ready,
                ))

            except Exception as exc:
                errors += 1
                error_message = str(exc)
                self.stderr.write(f"Row {row_number}: ERROR {error_message}")
                report_rows.append(make_report_row(
                    row_number=row_number,
                    action="error",
                    title=locals().get("title", ""),
                    city_slug=city_slug,
                    source_id=locals().get("source_id", ""),
                    dedupe_key=locals().get("dedupe_key", ""),
                    errors=[error_message],
                    missing_recommended_fields=locals().get("missing_recommended_fields", []),
                    discover_ready=False,
                ))

        if report_file:
            write_report_file(report_file, report_rows)
            self.stdout.write(f"Report written to {report_file}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no database changes were written."))
            self.stdout.write(self.style.SUCCESS(
                "Dry-run summary. "
                f"rows={len(df)} unique={len(seen)} would_create={created} "
                f"would_update={updated} would_skip={skipped} warnings={warnings} errors={errors} "
                f"duplicate_keys={len(duplicate_keys)}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. rows={len(df)} unique={len(seen)} created={created} updated={updated} skipped={skipped} errors={errors}"
            ))
