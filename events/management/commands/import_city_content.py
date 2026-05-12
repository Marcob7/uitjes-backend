import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from events.importing.city_content import CityContentWorkbook, DATA_TYPES
from events.importing.validators import CityContentValidator


class Command(BaseCommand):
    help = "Dry-run validator for city content Excel imports. Commit/import is intentionally not implemented yet."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx file.")
        parser.add_argument("--city", required=True, help="City slug, for example harderwijk.")
        parser.add_argument("--type", required=True, choices=sorted(DATA_TYPES), help="Import type: outings or food_drink.")
        parser.add_argument("--dry-run", action="store_true", help="Validate only. No database changes are written.")
        parser.add_argument("--commit", action="store_true", help="Reserved for future real imports. Not implemented yet.")
        parser.add_argument("--report-file", default="", help="Optional path for a JSON dry-run report.")
        parser.add_argument("--no-report-file", action="store_true", help="Print only; do not write the default JSON report.")

    def handle(self, *args, **options):
        if options["commit"]:
            self.stdout.write(self.style.ERROR("Commit/import is nog niet geïmplementeerd. Dry-run only."))
            return

        if not options["dry_run"]:
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

        report_path = ""
        if not options["no_report_file"]:
            report_path = options["report_file"] or self._default_report_path(options["city"], options["type"])
            self._write_report(report_path, report)

        self._print_summary(report, report_path)
        self.stdout.write(self.style.WARNING("DRY RUN ONLY: no database changes were written."))

    def _default_report_path(self, city_slug, data_type):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_city = city_slug.replace("/", "-").replace("\\", "-")
        return str(Path("import_reports") / f"{safe_city}_{data_type}_{timestamp}_dry_run.json")

    def _write_report(self, report_path, report):
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            "metadata": report["metadata"],
            "summary": report["summary"],
            "rows": [row.to_dict() for row in report["rows"]],
        }
        path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")

    def _print_summary(self, report, report_path):
        metadata = report["metadata"]
        summary = report["summary"]
        rows = report["rows"]

        self.stdout.write(self.style.SUCCESS("Dry-run validation complete."))
        self.stdout.write(f"File: {metadata['file_name']}")
        self.stdout.write(f"Sheet: {metadata['sheet']}")
        self.stdout.write(f"City: {metadata['city']}")
        self.stdout.write(f"Type: {metadata['type']}")
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
