from decimal import Decimal

from django.core.management.base import BaseCommand

from events.models import Event


class Command(BaseCommand):
    help = "Vult handmatig coordinaten in voor een paar Apeldoorn-events"

    def handle(self, *args, **options):
        updates = [
            {
                "title": "Record Store Day (Mansion24/Plato)",
                "address": "Hoofdstraat 124, Apeldoorn",
                "latitude": Decimal("52.215900"),
                "longitude": Decimal("5.964800"),
            },
            {
                "title": "StadsOase",
                "address": "Nieuwstraat 377, Apeldoorn",
                "latitude": Decimal("52.218300"),
                "longitude": Decimal("5.967700"),
            },
            {
                "title": "Royal Light Festival",
                "address": "Centrum Apeldoorn",
                "latitude": Decimal("52.211700"),
                "longitude": Decimal("5.969900"),
            },
        ]

        updated_count = 0

        for item in updates:
            try:
                event = Event.objects.get(title=item["title"], city__slug="apeldoorn")
            except Event.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f'Niet gevonden: {item["title"]}'
                    )
                )
                continue

            event.address = item["address"]
            event.latitude = item["latitude"]
            event.longitude = item["longitude"]
            event.save(update_fields=["address", "latitude", "longitude"])

            updated_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'Bijgewerkt: {event.title} -> {event.latitude}, {event.longitude}'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Klaar. {updated_count} event(s) bijgewerkt.")
        )