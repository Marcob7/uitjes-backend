# <jouw_app>/management/commands/import_events_excel.py
import re
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import make_aware

import pandas as pd
from events.models import City, Venue, Event

DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12
}


def norm(s):
    if s is None:
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def slug_simple(s):
    s = norm(s).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def parse_dutch_date_single(text):
    """
    Parse '7 februari 2026' -> aware datetime 09:00.
    """
    t = norm(text).lower()
    m = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", t)
    if not m:
        return None

    day = int(m.group(1))
    month = DUTCH_MONTHS.get(m.group(2))
    year = int(m.group(3))
    if not month:
        return None

    return make_aware(datetime(year, month, day, 9, 0, 0))


def parse_dutch_date_range(text):
    """
    Parse '14 februari – 2 maart 2026' (ook - / t/m) -> (start,end)
    Anders: (single_date, None)
    """
    raw = norm(text).lower()
    raw = raw.replace("–", "-").replace("—", "-")
    raw = raw.replace("t/m", "-").replace("tot en met", "-")

    m = re.search(r"(\d{1,2})\s+([a-z]+)\s*-\s*(\d{1,2})\s+([a-z]+)\s+(\d{4})", raw)
    if not m:
        return (parse_dutch_date_single(text), None)

    d1, m1, d2, m2, y = m.groups()
    d1 = int(d1); d2 = int(d2); y = int(y)
    mo1 = DUTCH_MONTHS.get(m1); mo2 = DUTCH_MONTHS.get(m2)
    if not mo1 or not mo2:
        return (None, None)

    start = make_aware(datetime(y, mo1, d1, 9, 0, 0))
    end = make_aware(datetime(y, mo2, d2, 17, 0, 0))
    return (start, end)


def build_dedupe_key(city_slug, title, date_text):
    base = f"{city_slug}|{slug_simple(title)}|{slug_simple(date_text or '')}"
    return base[:255]


def get_or_create_venue(city, venue_name):
    """
    Venue is optioneel. Als we geen duidelijke venue hebben: None.
    """
    name = norm(venue_name)
    if not name:
        return None

    venue, _ = Venue.objects.get_or_create(
        city=city,
        name=name,
        defaults={"address": ""},
    )
    return venue


class Command(BaseCommand):
    help = "Import events from an Excel file with dedupe + upsert (Apeldoorn/Deventer format)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Pad naar .xlsx")
        parser.add_argument("--city", required=True, help="City slug, bijv. apeldoorn of deventer")
        parser.add_argument("--source", default="excel", help="Bijv. excel_apeldoorn")

    @transaction.atomic
    def handle(self, *args, **opts):
        path = opts["file"]
        city_slug = norm(opts["city"]).lower()
        source = norm(opts["source"])

        city = City.objects.filter(slug=city_slug).first()
        if not city:
            raise Exception(f"City met slug '{city_slug}' niet gevonden. Maak die eerst aan in de admin/shell.")

        df = pd.read_excel(path)
        df.columns = [norm(c) for c in df.columns]

        created = updated = skipped = errors = 0
        seen = set()  # dedupe binnen excel

        for idx, row in df.iterrows():
            try:
                title = norm(row.get("Naam/Activiteit"))
                if not title:
                    skipped += 1
                    continue

                # Website -> source_url
                source_url = norm(row.get("Website")) or None

                # Datum tekst: Apeldoorn heeft 'Datum', Deventer heeft soms 'Datum' of 'Datum/Periode'
                date_text = norm(row.get("Datum")) or norm(row.get("Datum/Periode"))
                date_text = date_text or None

                # Omschrijving: Deventer gebruikt vaak 'Omschrijving' of 'Locatie/Omschrijving'
                description = norm(row.get("Omschrijving")) or norm(row.get("Locatie/Omschrijving"))
                description = description or None

                # Venue: we proberen 'Locatie/Omschrijving' eerst als venue naam te gebruiken (grof maar ok),
                # en anders leeg laten. Later kunnen we dit verfijnen.
                venue = None
                if not source_url:
                    # bij bestaande items staat locatie soms in Locatie/Omschrijving
                    venue = get_or_create_venue(city, row.get("Locatie/Omschrijving"))

                start_at = end_at = None
                if date_text:
                    start_at, end_at = parse_dutch_date_range(date_text)

                # dedupe: prefer source_url, anders dedupe_key
                dedupe_key = build_dedupe_key(city_slug, title, date_text)
                internal_key = source_url or f"{city_slug}|{dedupe_key}"
                if internal_key in seen:
                    skipped += 1
                    continue
                seen.add(internal_key)

                defaults = {
                    "title": title,
                    "city": city,
                    "venue": venue,
                    "description": description,
                    "start_at": start_at,
                    "end_at": end_at,
                    "source_url": source_url,
                    "date_text": date_text,
                    "source": source,
                    "dedupe_key": dedupe_key if not source_url else None,
                }

                if source_url:
                    obj, was_created = Event.objects.update_or_create(
                        source_url=source_url,
                        defaults=defaults,
                    )
                else:
                    obj, was_created = Event.objects.update_or_create(
                        city=city,
                        dedupe_key=dedupe_key,
                        defaults=defaults,
                    )

                if was_created:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                errors += 1
                self.stderr.write(f"Row {idx+2}: ERROR {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. rows={len(df)} unique={len(seen)} created={created} updated={updated} skipped={skipped} errors={errors}"
        ))