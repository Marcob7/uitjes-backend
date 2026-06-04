from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from events.models import Event


class Command(BaseCommand):
    help = "Rapporteert lifecycle-kandidaten voor events zonder data te wijzigen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximaal aantal voorbeeldrecords per sectie.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        now = timezone.now()

        expirable_kinds = [Event.Kind.EVENT, Event.Kind.FESTIVAL]
        expired_candidates = (
            Event.objects.select_related("city")
            .filter(kind__in=expirable_kinds)
            .filter(Q(end_at__lt=now) | (Q(end_at__isnull=True) & Q(start_at__lt=now)))
            .exclude(status=Event.Status.EXPIRED)
            .order_by("city__slug", "start_at", "title")
        )

        missing_clear_date = (
            Event.objects.select_related("city")
            .filter(start_at__isnull=True, end_at__isnull=True)
            .filter(
                (Q(date_text__isnull=True) | Q(date_text__exact=""))
                & (Q(raw_date_text__isnull=True) | Q(raw_date_text__exact=""))
                & (Q(opening_hours_text__isnull=True) | Q(opening_hours_text__exact=""))
            )
            .exclude(kind__in=[Event.Kind.PLACE, Event.Kind.FOOD_DRINK])
            .order_by("city__slug", "title")
        )

        lifecycle_counts = (
            Event.objects.filter(
                status__in=[
                    Event.Status.HIDDEN,
                    Event.Status.ARCHIVED,
                    Event.Status.EXPIRED,
                ]
            )
            .values("city__slug", "status")
            .annotate(count=Count("id"))
            .order_by("city__slug", "status")
        )

        duplicate_slugs = (
            Event.objects.exclude(slug__isnull=True)
            .exclude(slug__exact="")
            .values("city__slug", "slug")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .order_by("city__slug", "slug")
        )

        self.stdout.write("Event lifecycle check")
        self.stdout.write("=====================")
        self.stdout.write(f"Peildatum: {timezone.localtime(now).isoformat()}")
        self.stdout.write("")

        self._write_records(
            "Verlopen event-kandidaten",
            expired_candidates,
            limit,
            include_dates=True,
        )
        self._write_records(
            "Records zonder duidelijke datum mogelijk needs_review",
            missing_clear_date,
            limit,
            include_dates=False,
        )
        self._write_lifecycle_counts(lifecycle_counts)
        self._write_duplicate_slugs(duplicate_slugs, limit)

    def _write_records(self, title, queryset, limit, include_dates):
        count = queryset.count()
        self.stdout.write(f"{title}: {count}")

        for event in queryset[:limit]:
            city = event.city.slug if event.city_id else "-"
            line = f"- #{event.id} [{city}] {event.title} ({event.slug or '-'})"
            if include_dates:
                line += f" start_at={event.start_at or '-'} end_at={event.end_at or '-'}"
            self.stdout.write(line)

        if count > limit:
            self.stdout.write(f"... {count - limit} meer")
        self.stdout.write("")

    def _write_lifecycle_counts(self, lifecycle_counts):
        self.stdout.write("Hidden/archived/expired aantallen per stad:")

        has_rows = False
        for row in lifecycle_counts:
            has_rows = True
            city = row["city__slug"] or "-"
            self.stdout.write(f"- {city}: {row['status']}={row['count']}")

        if not has_rows:
            self.stdout.write("- geen")
        self.stdout.write("")

    def _write_duplicate_slugs(self, duplicate_slugs, limit):
        duplicates = list(duplicate_slugs[:limit])
        total = duplicate_slugs.count()
        self.stdout.write(f"Duplicate slugs per stad: {total}")

        for row in duplicates:
            city = row["city__slug"] or "-"
            self.stdout.write(f"- {city}: {row['slug']} ({row['count']} records)")

        if total > limit:
            self.stdout.write(f"... {total - limit} meer")
