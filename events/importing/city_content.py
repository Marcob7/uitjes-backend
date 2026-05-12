import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from django.utils.text import slugify


DATA_TYPES = {"outings", "food_drink"}

REQUIRED_FIELDS = [
    "city",
    "title",
    "slug",
    "kind",
    "category",
    "summary",
    "description",
    "source_url",
    "last_checked_at",
]

RECOMMENDED_FIELD_GROUPS = [
    ("venue_or_address", ("venue", "address")),
    ("latitude", ("latitude",)),
    ("longitude", ("longitude",)),
    ("image_url", ("image_url",)),
    ("tags", ("tag_values",)),
    ("raw_date_text_or_start_at", ("raw_date_text", "start_at")),
    ("price_note", ("price_note",)),
    ("indoor_outdoor", ("indoor_outdoor",)),
    ("weather_suitability", ("weather_suitability",)),
]

FIELD_ALIASES = {
    "city": ["City"],
    "title": ["Naam/Activiteit", "Naam/Restaurant", "Title", "Naam"],
    "slug": ["Slug"],
    "kind": ["Kind", "Type"],
    "category": ["Category", "Categorie"],
    "subcategory": ["SubCategory", "Subcategorie"],
    "raw_date_text": ["DatumRaw", "Datum", "Datum/Periode"],
    "start_at": ["StartAt"],
    "end_at": ["EndAt"],
    "venue": ["Venue", "Locatie"],
    "address": ["Address", "Adres"],
    "postal_code": ["PostalCode", "Postcode"],
    "latitude": ["Latitude", "Lat"],
    "longitude": ["Longitude", "Lng", "Lon"],
    "district": ["District", "Wijk"],
    "summary": ["Summary", "Samenvatting"],
    "description": ["Omschrijving", "Beschrijving", "Description"],
    "practical_info": ["PracticalInfo", "PraktischeInfo"],
    "website": ["Website"],
    "source_url": ["SourceUrl", "BronUrl", "BronURL"],
    "ticket_url": ["TicketUrl", "Tickets"],
    "reservation_url": ["ReservationUrl", "ReserverenUrl"],
    "image_url": ["ImageUrl", "Afbeelding"],
    "is_free": ["IsFree", "Gratis"],
    "price_min": ["PriceMin", "PrijsMin"],
    "price_max": ["PriceMax", "PrijsMax"],
    "price_note": ["PriceNote", "PrijsOpmerking"],
    "audience_tags": ["AudienceTags", "Audiences"],
    "moment_tags": ["MomentTags", "Moments"],
    "vibe_tags": ["VibeTags", "Vibes"],
    "theme_tags": ["ThemeTags", "Themes"],
    "feature_tags": ["FeatureTags", "Features"],
    "accessibility_tags": ["AccessibilityTags"],
    "indoor_outdoor": ["IndoorOutdoor", "BinnenBuiten"],
    "weather_suitability": ["WeatherSuitability", "WeerGeschikt"],
    "featured": ["Featured", "Uitgelicht"],
    "hidden_gem": ["HiddenGem", "Hidden Gem"],
    "source_id": ["SourceId", "BronId"],
    "external_id": ["ExternalId"],
    "venue_type": ["VenueType", "LocatieType"],
    "venue_website": ["VenueWebsite"],
    "organizer_name": ["OrganizerName"],
    "organizer_website": ["OrganizerWebsite"],
    "last_checked_at": ["LastCheckedAt", "LaatstGecontroleerd"],
    "data_quality_note": ["DataQualityNote", "DatakwaliteitNotitie"],
}

OUTING_KIND_VALUES = {
    "event",
    "evenement",
    "activity",
    "activiteit",
    "uitje",
    "festival",
    "place",
    "plek",
    "locatie",
    "market",
    "markt",
    "museum",
    "workshop",
}

FOOD_KIND_VALUES = {
    "bakery",
    "bakkerij",
    "bistro",
    "brasserie",
    "food",
    "food_drink",
    "eten",
    "eten-drinken",
    "horeca",
    "coffee",
    "koffie",
    "koffiebar",
    "restaurant",
    "restaurants",
    "cafe",
    "café",
    "eetcafe",
    "eetcafé",
    "bar",
    "fastfood",
    "fast_casual",
    "fine_dining",
    "casual_dining",
    "grand_cafe",
    "grand_café",
    "lunch",
    "lunchroom",
}

FOOD_HINTS = {
    "bakery",
    "bakkerij",
    "bistro",
    "brasserie",
    "restaurant",
    "eten",
    "drinken",
    "food",
    "horeca",
    "coffee",
    "koffie",
    "koffiebar",
    "cafe",
    "café",
    "eetcafe",
    "eetcafé",
    "bar",
    "lunch",
    "diner",
    "fastfood",
    "fast casual",
    "fine dining",
    "casual dining",
    "grand café",
    "ijssalon",
    "wereldkeuken",
    "viswinkel",
}

CATEGORY_ALIASES = {
    "attractie": "Activiteit",
    "bakery": "Eten & drinken",
    "bakkerij": "Eten & drinken",
    "bar": "Eten & drinken",
    "bezienswaardigheid": "Cultuur",
    "bijzondere locatie": "Activiteit",
    "brasserie": "Eten & drinken",
    "cafe": "Eten & drinken",
    "café": "Eten & drinken",
    "casual dining": "Eten & drinken",
    "community": "Activiteit",
    "concert": "Muziek",
    "culinair": "Eten & drinken",
    "culinaire tour": "Eten & drinken",
    "eetcafe": "Eten & drinken",
    "eetcafé": "Eten & drinken",
    "erfgoed": "Cultuur",
    "evenement": "Activiteit",
    "expositie": "Cultuur",
    "fast casual": "Eten & drinken",
    "fastfood": "Eten & drinken",
    "fine dining": "Eten & drinken",
    "grand cafe": "Eten & drinken",
    "grand café": "Eten & drinken",
    "hobby": "Activiteit",
    "hotelrestaurant": "Eten & drinken",
    "ijssalon": "Eten & drinken",
    "kinderen": "Met kinderen",
    "koffie": "Eten & drinken",
    "koffiebar": "Eten & drinken",
    "lunch": "Eten & drinken",
    "lunchroom": "Eten & drinken",
    "markt": "Activiteit",
    "museum": "Cultuur",
    "natuur": "Buiten",
    "natuurpaviljoen": "Buiten",
    "park": "Buiten",
    "restaurant": "Eten & drinken",
    "roadhouse": "Eten & drinken",
    "rondleiding": "Cultuur",
    "speciaalzaak": "Eten & drinken",
    "sport": "Activiteit",
    "sportief": "Activiteit",
    "theater": "Cultuur",
    "uitgaan": "Cultuur",
    "viswinkel": "Eten & drinken",
    "wereldkeuken": "Eten & drinken",
    "winkelen": "Activiteit",
    "workshop": "Activiteit",
}


def normalize_text(value):
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_column(value):
    return normalize_text(value).casefold()


def split_tags(value):
    raw = normalize_text(value)
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[;,|]", raw) if part.strip()]


def parse_decimal(value):
    raw = normalize_text(value)
    if not raw:
        return None
    raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def parse_excel_date(value):
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return normalize_text(value)


def normalize_kind(raw_kind, data_type):
    value = normalize_text(raw_kind).casefold().replace(" ", "_").replace("-", "_")
    if not value and data_type == "food_drink":
        return "food_drink"
    normalized_food_values = {item.replace("-", "_").replace(" ", "_") for item in FOOD_KIND_VALUES}
    if value in normalized_food_values or value in {"eten_drinken"}:
        return "food_drink"
    if value in {"activiteit", "uitje"}:
        return "activity"
    if value in {"evenement"}:
        return "event"
    if value in {"plek", "locatie", "museum"}:
        return "place"
    if value in {"market", "markt", "workshop"}:
        return "activity"
    if value in {"event", "activity", "festival", "place", "food_drink"}:
        return value
    return value


def normalize_category(raw_category):
    value = normalize_text(raw_category)
    return CATEGORY_ALIASES.get(value.casefold(), value)


def content_fingerprint(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class ImportRecord:
    row_number: int
    raw: dict
    city: str = ""
    title: str = ""
    slug: str = ""
    kind: str = ""
    category: str = ""
    subcategory: str = ""
    summary: str = ""
    description: str = ""
    source_url: str = ""
    last_checked_at: str = ""
    venue: str = ""
    address: str = ""
    postal_code: str = ""
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    raw_latitude: str = ""
    raw_longitude: str = ""
    raw_date_text: str = ""
    start_at: str = ""
    end_at: str = ""
    image_url: str = ""
    price_note: str = ""
    indoor_outdoor: str = ""
    weather_suitability: str = ""
    source_id: str = ""
    tag_values: list[str] = field(default_factory=list)


class CityContentWorkbook:
    def __init__(self, path, city_slug, data_type):
        self.path = Path(path)
        self.city_slug = normalize_text(city_slug).casefold()
        self.data_type = data_type

    def read(self):
        if self.data_type not in DATA_TYPES:
            raise ValueError(f"Unsupported type '{self.data_type}'. Expected one of: {', '.join(sorted(DATA_TYPES))}")
        if not self.path.exists():
            raise FileNotFoundError(f"Excel file not found: {self.path}")

        xls = pd.ExcelFile(self.path)
        sheet_name = self._pick_sheet(xls)
        df = pd.read_excel(self.path, sheet_name=sheet_name)
        df = df.dropna(how="all").copy()
        df.columns = [normalize_text(column) for column in df.columns]
        records = [self._row_to_record(index + 2, row) for index, row in df.iterrows()]

        return {
            "file": str(self.path),
            "file_name": self.path.name,
            "file_sha256": content_fingerprint(self.path),
            "sheet": sheet_name,
            "columns": list(df.columns),
            "records": records,
        }

    def _pick_sheet(self, xls):
        candidates = []
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(self.path, sheet_name=sheet_name, nrows=2)
            columns = {normalize_column(column) for column in df.columns}
            title_columns = {normalize_column(alias) for alias in FIELD_ALIASES["title"]}
            score = 0
            if sheet_name.casefold() in {"master template", "sheet", "sheet1"}:
                score += 4
            if columns & title_columns:
                score += 5
            if normalize_column("SourceUrl") in columns:
                score += 2
            if normalize_column("LastCheckedAt") in columns:
                score += 2
            if len(columns) >= 20:
                score += 3
            if normalize_column("SourceId") in columns and "source" in sheet_name.casefold():
                score -= 4
            if "source" in sheet_name.casefold() or "geo" in sheet_name.casefold():
                score -= 6
            candidates.append((score, sheet_name))

        candidates.sort(reverse=True)
        if not candidates or candidates[0][0] <= 0:
            raise ValueError("No usable data sheet found. Expected a sheet with Naam/Activiteit or Naam/Restaurant.")
        return candidates[0][1]

    def _row_to_record(self, row_number, row):
        raw = {normalize_text(key): value for key, value in row.items()}

        def value(field_name):
            for alias in FIELD_ALIASES[field_name]:
                if alias in raw:
                    text = normalize_text(raw.get(alias))
                    if text:
                        return text
            return ""

        title = value("title")
        raw_kind = value("kind")
        record = ImportRecord(
            row_number=row_number,
            raw=raw,
            city=value("city") or self.city_slug,
            title=title,
            slug=value("slug") or slugify(title),
            kind=normalize_kind(raw_kind, self.data_type),
            category=normalize_category(value("category")),
            subcategory=value("subcategory"),
            summary=value("summary"),
            description=value("description"),
            source_url=value("source_url"),
            last_checked_at=parse_excel_date(raw.get("LastCheckedAt")),
            venue=value("venue"),
            address=value("address"),
            postal_code=value("postal_code"),
            raw_latitude=value("latitude"),
            raw_longitude=value("longitude"),
            raw_date_text=value("raw_date_text"),
            start_at=parse_excel_date(raw.get("StartAt")),
            end_at=parse_excel_date(raw.get("EndAt")),
            image_url=value("image_url"),
            price_note=value("price_note"),
            indoor_outdoor=value("indoor_outdoor").casefold(),
            weather_suitability=value("weather_suitability").casefold(),
            source_id=value("source_id"),
        )
        record.latitude = parse_decimal(record.raw_latitude)
        record.longitude = parse_decimal(record.raw_longitude)

        for field_name in ["audience_tags", "moment_tags", "vibe_tags", "theme_tags", "feature_tags", "accessibility_tags"]:
            record.tag_values.extend(split_tags(value(field_name)))

        return record


def expected_columns_for(data_type):
    return {
        "City",
        "Slug",
        "Kind",
        "Category",
        "Summary",
        "Omschrijving",
        "SourceUrl",
        "LastCheckedAt",
        "Latitude",
        "Longitude",
    }
