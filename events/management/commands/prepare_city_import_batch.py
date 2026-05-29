from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from events.importing.city_content import DATA_TYPES
from events.importing.prepare_city_import import (
    prepare_city_import_batch,
    write_prepare_json,
    write_prepare_report,
)


class Command(BaseCommand):
    help = "Prepare a city-content Excel batch by normalizing cells and auto-fixing date-series duplicate titles."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx file.")
        parser.add_argument("--city", required=True, help="City slug, for example nijmegen.")
        parser.add_argument("--type", required=True, choices=sorted(DATA_TYPES), help="Import type: outings or food_drink.")
        parser.add_argument("--output-file", default="", help="Optional cleaned output path. Defaults to <original>_prepared.xlsx.")
        parser.add_argument("--write-report", action="store_true", help="Write a compact markdown report.")
        parser.add_argument("--report-file", default="", help="Optional markdown report path when --write-report is used.")
        parser.add_argument("--json-report-file", default="", help="Optional JSON details path for auditing.")
        parser.add_argument("--dry-run-after-clean", action="store_true", help="Run import_city_content --dry-run on the cleaned file.")

    def handle(self, *args, **options):
        try:
            result = prepare_city_import_batch(
                path=options["file"],
                city_slug=options["city"],
                data_type=options["type"],
                output_path=options["output_file"] or None,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if options["json_report_file"]:
            write_prepare_json(result, options["json_report_file"])

        if options["write_report"]:
            report_path = options["report_file"] or self._default_report_path(result.output_file)
            write_prepare_report(result, report_path)

        if options["dry_run_after_clean"] and result.ready_for_dry_run:
            call_command(
                "import_city_content",
                file=result.output_file,
                city=options["city"],
                type=options["type"],
                dry_run=True,
                no_report_file=True,
                stdout=self.stdout,
                stderr=self.stderr,
            )

        self._print_compact_summary(result)

    def _default_report_path(self, output_file):
        output = Path(output_file)
        return str(output.with_name(f"{output.stem}_prepare_report.md"))

    def _print_compact_summary(self, result):
        self.stdout.write("")
        self.stdout.write(f"City: {result.city.title()}")
        self.stdout.write(f"File: {Path(result.input_file).name}")
        self.stdout.write(f"Rows: {result.rows}")
        self.stdout.write(f"Blocking issues: {len(result.blocking)}")
        self.stdout.write(f"Warnings: {len(result.warnings)}")
        self.stdout.write(f"Auto fixes: {result.auto_fixed_titles} titles, {result.normalized_url_fields} URL fields")
        self.stdout.write(f"Cleaned file: {result.output_file}")
        self.stdout.write(f"Ready for dry-run: {'yes' if result.ready_for_dry_run else 'no'}")

        if result.blocking:
            self.stdout.write("")
            self.stdout.write("Blocking issue examples:")
            for issue in result.blocking[:10]:
                self.stdout.write(f"  row {issue.row_number}: {issue.code} - {issue.message}")
