import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from django.utils.timezone import make_aware

from events.importing.city_content import CityContentWorkbook, DATA_TYPES
from events.importing.validators import CityContentValidator
from events.models import Category, City, Event, Tag, Venue


class Command(BaseCommand):
    help = "Validate city content Excel imports and safely create new records when --commit is explicit."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx file.")
        parser.add_argument("--city", required=True, help="City slug, for example harderwijk.")
        parser.add_argument("--type", required=True, choices=sorted(DATA_TYPES), help="Import type: outings or food_drink.")
        parser.add_argument("--dry-run", action="store_true", help="Validate only. No database changes are written.")
        parser.add_argument("--commit", action="store_true", help="Create new records for valid, non-duplicate rows.")
        parser.add_argument("--report-file", default="", help="Optional path for a JSON report.")
        parser.add_argument("--no-report-file", action="store_true", help="Print only; do not write the default JSON report.")

    def handle(self, *args, **options):
        if options["dry_run"] and options["commit"]:
            raise CommandError("Use --dry-run or --commit, not both. Nothing was imported.")

        commit = options["commit"]
        mode = "commit" if commit else "dry_run"

        if not commit and not options["dry_run"]:
            self.stdout.write(self.style.WARNING("Geen --dry-run opgegeven; veilige default actief. Er worden geen databasewijzigingen gedaan."))

        workbook = CityContentWorkbook(
            path=options["file"],
            city_slug=options["city"],
            data_type=options["type"],
        )

        try:
            payload = workbook.read()
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        validator = CityContentValidator(
            city_slug=options["city"],
            data_type=options["type"],
        )
        report = validator.validate(payload)
        report["metadata"]["mode"] = mode
        report["metadata"]["import_batch"] = "not_registered"
        report["metadata"]["import_batch_note"] = "ImportBatch/ImportSource model is not present; add registration later if needed."

        import_result = self._empty_import_result(report["summary"])
        if commit:
            import_result = self._commit_valid_rows(
                payload=payload,
                report=report,
                city_slug=options["city"],
                data_type=options["type"],
            )
        self._extend_summary(report, import_result, mode)

        report_path = ""
        if not options["no_report_file"]:
            report_path = options["report_file"] or self._default_report_path(options["city"], options["type"], mode)
            self._write_report(report_path, report)

        self._print_summary(report, report_path, mode)
        if commit:
            self.stdout.write(self.style.SUCCESS("COMMIT complete: valid new rows were created; errors and duplicates were skipped."))
        else:
            self.stdout.write(self.style.WARNING("DRY RUN ONLY: no database changes were written."))

    def _default_report_path(self, city_slug, data_type, mode):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_city = city_slug.replace("/", "-").replace("\\", "-")
        suffix = "commit" if mode == "commit" else "dry_run"
        return str(Path("import_reports") / f"{safe_city}_{data_type}_{timestamp}_{suffix}.json")

    def _write_report(self, report_path, report):
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            "metadata": report["metadata"],
            "summary": report["summary"],
            "rows": [row.to_dict() for row in report["rows"]],
        }
        path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")

    def _print_summary(self, report, report_path, mode):
        metadata = report["metadata"]
        summary = report["summary"]
        rows = report["rows"]

        label = "COMMIT" if mode == "commit" else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(f"{label} validation complete."))
        self.stdout.write(f"File: {metadata['file_name']}")
        self.stdout.write(f"Sheet: {metadata['sheet']}")
        self.stdout.write(f"City: {metadata['city']}")
        self.stdout.write(f"Type: {metadata['type']}")
        self.stdout.write(f"Mode: {label}")
        if report_path:
            self.stdout.write(f"Report: {report_path}")

        self.stdout.write("")
        self.stdout.write("Summary:")
        self.stdout.write(f"  total_rows: {summary['total_rows']}")
        self.stdout.write(f"  valid_rows: {summary['valid_rows']}")
        self.stdout.write(f"  rows_with_warnings: {summary['rows_with_warnings']}")
        self.stdout.write(f"  rows_with_errors: {summary['rows_with_errors']}")
        self.stdout.write(f"  missing_required_fields: {summary['missing_required_fields']}")
        self.stdout.write(f"  missing_coordinates: {summary['missing_coordinates']}")
        self.stdout.write(f"  missing_source_urls: {summary['missing_source_urls']}")
        self.stdout.write(f"  duplicate_slugs: {summary['duplicate_slugs']}")
        self.stdout.write(f"  possible_duplicates: {summary['possible_duplicates']}")
        self.stdout.write(f"  unknown_categories: {summary['unknown_categories']}")
        self.stdout.write(f"  incomplete_dates: {summary['incomplete_dates']}")
        self.stdout.write(f"  imported_rows: {summary['imported_rows']}")
        self.stdout.write(f"  skipped_error_rows: {summary['skipped_error_rows']}")
        self.stdout.write(f"  skipped_duplicate_rows: {summary['skipped_duplicate_rows']}")
        self.stdout.write(f"  not_imported_rows: {summary['not_imported_rows']}")
        self.stdout.write(f"  advice: {summary['advice']}")

        interesting = [row for row in rows if row.errors or row.warnings][:10]
        if interesting:
            self.stdout.write("")
            self.stdout.write("First issues:")
            for row in interesting:
                messages = row.errors or row.warnings
                self.stdout.write(
                    f"  row {row.row_number} [{row.severity}] {row.title or '(no title)'}: "
                    f"{'; '.join(messages[:4])}"
                )

    def _empty_import_result(self, summary):
        return {
            "imported_rows": 0,
            "skipped_error_rows": summary["rows_with_errors"],
            "skipped_duplicate_rows": 0,
            "not_imported_rows": summary["total_rows"],
            "row_results": {},
        }

    def _extend_summary(self, report, import_result, mode):
        summary = report["summary"]
        summary.update(
            {
                "mode": mode,
                "dry_run": mode != "commit",
                "commit": mode == "commit",
                "source_file_name": report["metadata"]["file_name"],
                "city": report["metadata"]["city"],
                "type": report["metadata"]["type"],
                "imported_rows": import_result["imported_rows"],
                "skipped_error_rows": import_result["skipped_error_rows"],
                "skipped_duplicate_rows": import_result["skipped_duplicate_rows"],
                "not_imported_rows": import_result["not_imported_rows"],
            }
        )

        row_results = import_result.get("row_results", {})
        for row in report["rows"]:
            result = row_results.get(row.row_number)
            if not result:
                continue
            row.action = result["action"]
            if result.get("warning"):
                row.warnings.append(result["warning"])
            if result.get("error"):
                row.errors.append(result["error"])

    def _commit_valid_rows(self, payload, report, city_slug, data_type):
        city_slug = city_slug.casefold()
        city, _ = City.objects.get_or_create(
            slug=city_slug,
            defaults={"name": city_slug.replace("-", " ").title()},
        )

        rows_by_number = {row.row_number: row for row in report["rows"]}
        imported = 0
        skipped_errors = 0
        skipped_duplicates = 0
        row_results = {}
        seen_keys = set()

        for record in payload["records"]:
            validation_row = rows_by_number[record.row_number]
            if validation_row.errors:
                skipped_errors += 1
                row_results[record.row_number] = {
                    "action": "skipped_error",
                    "error": "not imported because row has blocking validation errors",
                }
                continue

            duplicate = self._find_duplicate(city=city, record=record)
            file_key = self._file_duplicate_key(city_slug, record)
            if file_key in seen_keys or duplicate:
                skipped_duplicates += 1
                row_results[record.row_number] = {
                    "action": "skipped_duplicate",
                    "warning": "duplicate skipped; existing records are not overwritten",
                }
                continue
            seen_keys.add(file_key)

            try:
                with transaction.atomic():
                    event = self._create_event(city=city, record=record, data_type=data_type)
                    self._attach_tags(event, record)
            except Exception as exc:
                skipped_errors += 1
                row_results[record.row_number] = {
                    "action": "skipped_error",
                    "error": f"import failed for row {record.row_number}: {exc}",
                }
                self.stderr.write(f"Row {record.row_number}: ERROR import failed: {exc}")
                continue

            imported += 1
            row_results[record.row_number] = {"action": "imported"}

        total_rows = report["summary"]["total_rows"]
        return {
            "imported_rows": imported,
            "skipped_error_rows": skipped_errors,
            "skipped_duplicate_rows": skipped_duplicates,
            "not_imported_rows": total_rows - imported,
            "row_results": row_results,
        }

    def _find_duplicate(self, city, record):
        query = Q(city=city, slug=record.slug, kind=record.kind)
        if record.source_url:
            query |= Q(source_url=record.source_url)
        return Event.objects.filter(query).first()

    def _file_duplicate_key(self, city_slug, record):
        return (
            city_slug,
            record.slug,
            record.kind,
        )

    def _create_event(self, city, record, data_type):
        category = self._find_category(record.category)
        venue = self._get_or_create_venue(city, record)
        return Event.objects.create(
            title=record.title,
            slug=record.slug,
            kind=record.kind,
            city=city,
            venue=venue,
            category=category,
            description=record.description or None,
            summary=record.summary or None,
            image_url=record.image_url or None,
            ticket_url=self._record_raw_value(record, "TicketUrl") or None,
            address=record.address or None,
            latitude=record.latitude,
            longitude=record.longitude,
            start_at=self._parse_datetime(record.start_at),
            end_at=self._parse_datetime(record.end_at),
            is_free=self._parse_bool(self._record_raw_value(record, "IsFree") or self._record_raw_value(record, "Gratis")),
            price_note=record.price_note or None,
            source_url=record.source_url or None,
            date_text=record.raw_date_text or None,
            raw_date_text=record.raw_date_text or None,
            source=f"city_content:{data_type}",
            dedupe_key=self._build_dedupe_key(city.slug, record),
            indoor_outdoor=record.indoor_outdoor if record.indoor_outdoor in {"indoor", "outdoor", "both"} else None,
            weather_suitability=record.weather_suitability if record.weather_suitability in {"all", "sun", "rain"} else None,
            is_featured=self._parse_bool(self._record_raw_value(record, "Featured") or self._record_raw_value(record, "Uitgelicht")),
            is_hidden_gem=self._parse_bool(self._record_raw_value(record, "HiddenGem") or self._record_raw_value(record, "Hidden Gem")),
        )

    def _build_dedupe_key(self, city_slug, record):
        return f"{city_slug}|{record.slug}|{record.kind}"[:255]

    def _find_category(self, category_name):
        if not category_name:
            return None
        slug = slugify(category_name)
        return Category.objects.filter(Q(slug=slug) | Q(name__iexact=category_name)).first()

    def _get_or_create_venue(self, city, record):
        if not record.venue:
            return None
        venue, _ = Venue.objects.get_or_create(
            city=city,
            name=record.venue,
            defaults={
                "slug": slugify(f"{record.venue}-{city.slug}") or None,
                "address": record.address or "",
                "postal_code": record.postal_code or None,
                "website": self._record_raw_value(record, "VenueWebsite") or None,
                "venue_type": self._record_raw_value(record, "VenueType") or None,
                "latitude": record.latitude,
                "longitude": record.longitude,
            },
        )
        return venue

    def _attach_tags(self, event, record):
        tags = []
        for tag_name in record.tag_values:
            tag_slug = slugify(tag_name)
            if not tag_slug:
                continue
            tag, _ = Tag.objects.get_or_create(
                slug=tag_slug,
                defaults={
                    "name": tag_name,
                    "facet": Tag.Facet.THEME,
                    "is_active": True,
                },
            )
            tags.append(tag)
        if tags:
            event.tags.set(tags)

    def _record_raw_value(self, record, column):
        value = record.raw.get(column)
        if value is None:
            return ""
        return str(value).strip()

    def _parse_bool(self, value):
        normalized = (value or "").strip().casefold()
        return normalized in {"1", "true", "yes", "ja", "y"}

    def _parse_datetime(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo:
            return parsed
        return make_aware(parsed)
