from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from django.db.models import Q
from django.utils.text import slugify

from events.models import Category, Event
from events.importing.city_content import (
    FOOD_HINTS,
    FOOD_KIND_VALUES,
    RECOMMENDED_FIELD_GROUPS,
    REQUIRED_FIELDS,
    expected_columns_for,
    normalize_text,
)


@dataclass
class RowValidationResult:
    row_number: int
    action: str
    severity: str
    title: str
    slug: str
    city: str
    kind: str
    source_url: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    possible_duplicate_ids: list[int] = field(default_factory=list)
    discover_ready: bool = False

    def to_dict(self):
        data = asdict(self)
        data["errors"] = "; ".join(self.errors)
        data["warnings"] = "; ".join(self.warnings)
        data["missing_fields"] = "; ".join(self.missing_fields)
        data["possible_duplicate_ids"] = ",".join(str(item) for item in self.possible_duplicate_ids)
        return data


class CityContentValidator:
    def __init__(self, city_slug, data_type):
        self.city_slug = normalize_text(city_slug).casefold()
        self.data_type = data_type
        self.known_category_slugs = set(Category.objects.values_list("slug", flat=True))
        self.known_category_names = {
            normalize_text(name).casefold()
            for name in Category.objects.values_list("name", flat=True)
        }

    def validate(self, workbook_payload):
        columns = set(workbook_payload["columns"])
        column_warnings = self._validate_columns(columns)
        records = workbook_payload["records"]
        slug_counts = Counter(record.slug for record in records if record.slug)
        name_city_counts = Counter(
            (record.title.casefold(), record.city.casefold())
            for record in records
            if record.title and record.city
        )
        name_address_counts = Counter(
            (record.title.casefold(), record.address.casefold())
            for record in records
            if record.title and record.address
        )

        rows = []
        for record in records:
            result = self._validate_record(
                record=record,
                slug_counts=slug_counts,
                name_city_counts=name_city_counts,
                name_address_counts=name_address_counts,
            )
            result.warnings.extend(column_warnings)
            rows.append(result)

        return {
            "metadata": {
                "file": workbook_payload["file"],
                "file_name": workbook_payload["file_name"],
                "file_sha256": workbook_payload["file_sha256"],
                "sheet": workbook_payload["sheet"],
                "city": self.city_slug,
                "type": self.data_type,
                "columns": workbook_payload["columns"],
            },
            "rows": rows,
            "summary": self._build_summary(rows),
        }

    def _validate_columns(self, columns):
        warnings = []
        expected = expected_columns_for(self.data_type)
        normalized_columns = {column.casefold() for column in columns}
        missing = sorted(column for column in expected if column.casefold() not in normalized_columns)
        title_present = {"naam/activiteit", "naam/restaurant"} & normalized_columns
        if not title_present:
            missing.append("Naam/Activiteit or Naam/Restaurant")
        if missing:
            warnings.append(f"missing expected columns: {', '.join(sorted(set(missing)))}")
        return warnings

    def _validate_record(self, record, slug_counts, name_city_counts, name_address_counts):
        errors = []
        warnings = []
        missing_fields = []

        values = {
            "city": record.city,
            "title": record.title,
            "slug": record.slug,
            "kind": record.kind,
            "category": record.category,
            "summary": record.summary,
            "description": record.description,
            "source_url": record.source_url,
            "last_checked_at": record.last_checked_at,
        }

        for field_name in REQUIRED_FIELDS:
            if not normalize_text(values.get(field_name)):
                errors.append(f"missing required field: {field_name}")
                missing_fields.append(field_name)

        if record.city and record.city.casefold() != self.city_slug:
            errors.append(f"city mismatch: row city '{record.city}' does not match --city '{self.city_slug}'")

        if self._is_type_mismatch(record):
            errors.append(f"type mismatch: row looks like '{record.kind or record.category}' but command type is '{self.data_type}'")

        if record.raw_latitude and record.latitude is None:
            errors.append(f"invalid latitude: {record.raw_latitude}")
        if record.raw_longitude and record.longitude is None:
            errors.append(f"invalid longitude: {record.raw_longitude}")
        if record.latitude is not None and not (-90 <= record.latitude <= 90):
            errors.append(f"invalid latitude range: {record.latitude}")
        if record.longitude is not None and not (-180 <= record.longitude <= 180):
            errors.append(f"invalid longitude range: {record.longitude}")

        if not record.source_url:
            warnings.append("missing SourceUrl")
        elif not self._looks_like_url(record.source_url):
            warnings.append("SourceUrl is not a full URL")
        if not record.last_checked_at:
            warnings.append("missing LastCheckedAt")
        if record.latitude is None or record.longitude is None:
            warnings.append("missing Latitude/Longitude")
        if record.slug and slug_counts[record.slug] > 1:
            warnings.append(f"duplicate slug in file: {record.slug}")
        if record.title and record.city and name_city_counts[(record.title.casefold(), record.city.casefold())] > 1:
            warnings.append("duplicate name + city in file")
        if record.title and record.address and name_address_counts[(record.title.casefold(), record.address.casefold())] > 1:
            warnings.append("duplicate name + address in file")

        if not record.category:
            warnings.append("unknown or empty category")
        elif not self._category_known(record.category):
            warnings.append(f"unknown category: {record.category}")

        if not record.summary or len(record.summary) < 20:
            warnings.append("summary is empty or too short")
        if not record.description or len(record.description) < 40:
            warnings.append("description is empty or too short")
        if self._requires_date(record) and not record.raw_date_text and not record.start_at and not record.end_at:
            warnings.append("incomplete date: missing raw_date_text or start_at")

        for group_name, field_names in self._recommended_field_groups(record):
            if not any(self._record_value(record, field_name) for field_name in field_names):
                warnings.append(f"missing recommended field: {group_name}")

        duplicate_ids = self._find_database_duplicates(record)
        if duplicate_ids:
            warnings.append("possible duplicate in database")

        if errors:
            severity = "error"
            action = "would_skip"
        elif warnings:
            severity = "warning"
            action = "would_validate_with_warnings"
        else:
            severity = "ok"
            action = "would_validate"

        discover_ready = not errors and not any(
            warning.startswith("missing recommended field")
            for warning in warnings
        )

        return RowValidationResult(
            row_number=record.row_number,
            action=action,
            severity=severity,
            title=record.title,
            slug=record.slug,
            city=record.city,
            kind=record.kind,
            source_url=record.source_url,
            errors=errors,
            warnings=warnings,
            missing_fields=missing_fields,
            possible_duplicate_ids=duplicate_ids,
            discover_ready=discover_ready,
        )

    def _category_known(self, category):
        value = normalize_text(category)
        return value.casefold() in self.known_category_names or slugify(value) in self.known_category_slugs

    def _is_type_mismatch(self, record):
        kind = normalize_text(record.kind).casefold()
        category = normalize_text(record.category).casefold()
        subcategory = normalize_text(record.subcategory).casefold()
        combined = " ".join([kind, category, subcategory, record.title.casefold()])
        normalized_food_values = {item.replace("-", "_").replace(" ", "_") for item in FOOD_KIND_VALUES}

        if self.data_type == "food_drink":
            return not (
                kind in normalized_food_values
                or kind == "food_drink"
                or any(hint in combined for hint in FOOD_HINTS)
            )

        return kind == "food_drink" or kind in normalized_food_values or category in normalized_food_values

    def _requires_date(self, record):
        if self.data_type == "outings":
            return True

        combined = " ".join(
            [
                normalize_text(record.kind).casefold(),
                normalize_text(record.category).casefold(),
                normalize_text(record.subcategory).casefold(),
                normalize_text(record.raw_date_text).casefold(),
            ]
        )
        temporary_terms = {"event", "evenement", "festival", "workshop", "markt", "concert"}
        return any(term in combined for term in temporary_terms)

    def _recommended_field_groups(self, record):
        for group_name, field_names in RECOMMENDED_FIELD_GROUPS:
            if group_name == "raw_date_text_or_start_at" and not self._requires_date(record):
                continue
            yield group_name, field_names

    def _looks_like_url(self, value):
        parsed = urlparse(normalize_text(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _record_value(self, record, field_name):
        value = getattr(record, field_name)
        if isinstance(value, list):
            return bool(value)
        return bool(normalize_text(value))

    def _find_database_duplicates(self, record):
        if not record.title:
            return []

        query = Q(city__slug=self.city_slug, title__iexact=record.title)
        if record.address:
            query |= Q(city__slug=self.city_slug, title__iexact=record.title, address__iexact=record.address)
            query |= Q(city__slug=self.city_slug, title__iexact=record.title, venue__address__iexact=record.address)
        if record.source_url:
            query |= Q(source_url=record.source_url)

        return list(Event.objects.filter(query).values_list("id", flat=True)[:10])

    def _build_summary(self, rows):
        missing_required = defaultdict(int)
        for row in rows:
            for field_name in row.missing_fields:
                missing_required[field_name] += 1

        missing_coordinates = sum(
            1
            for row in rows
            if any("Latitude/Longitude" in warning for warning in row.warnings)
        )
        missing_sources = sum(1 for row in rows if "source_url" in row.missing_fields)
        duplicate_slugs = sum(
            1
            for row in rows
            if any("duplicate slug in file" in warning for warning in row.warnings)
        )
        possible_duplicates = sum(1 for row in rows if row.possible_duplicate_ids)
        unknown_categories = sum(
            1
            for row in rows
            if any("unknown category" in warning or "unknown or empty category" in warning for warning in row.warnings)
        )
        incomplete_dates = sum(
            1
            for row in rows
            if any("incomplete date" in warning for warning in row.warnings)
        )
        error_rows = sum(1 for row in rows if row.errors)
        warning_rows = sum(1 for row in rows if row.warnings and not row.errors)
        valid_rows = sum(1 for row in rows if not row.errors)

        return {
            "total_rows": len(rows),
            "valid_rows": valid_rows,
            "rows_with_warnings": warning_rows,
            "rows_with_errors": error_rows,
            "missing_required_fields": dict(sorted(missing_required.items())),
            "missing_coordinates": missing_coordinates,
            "missing_source_urls": missing_sources,
            "duplicate_slugs": duplicate_slugs,
            "possible_duplicates": possible_duplicates,
            "unknown_categories": unknown_categories,
            "incomplete_dates": incomplete_dates,
            "advice": "do_not_import" if error_rows else "review_warnings_then_import",
        }
