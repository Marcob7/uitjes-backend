from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from events.events_newsletter import build_events_newsletter_preview


CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


class Command(BaseCommand):
    help = (
        "Build a local events newsletter test email and print it via Django's "
        "console email backend. This never sends bulk email."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="to_email",
            required=True,
            help="Explicit test recipient address. Required; subscribers are never used.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of event blocks to include, capped at 5.",
        )

    def handle(self, *args, **options):
        to_email = (options["to_email"] or "").strip()

        try:
            validate_email(to_email)
        except ValidationError as exc:
            raise CommandError("Geef een geldig testadres op met --to.") from exc

        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit moet minimaal 1 zijn.")

        preview = build_events_newsletter_preview(limit=limit)

        if not preview.events:
            raise CommandError("Geen evenementendata beschikbaar voor de testmail.")

        connection = get_connection(
            backend=CONSOLE_BACKEND,
            stream=self.stdout,
        )
        message = EmailMessage(
            subject=preview.subject,
            body=preview.body,
            from_email="local-test@uitjes.test",
            to=[to_email],
            connection=connection,
        )
        sent_count = message.send(fail_silently=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Lokale evenementennieuwsbrief-testmail gegenereerd voor {to_email}."
            )
        )
        if preview.uses_fallback_data:
            self.stdout.write(
                self.style.WARNING(
                    "Let op: deze testmail gebruikt gemarkeerde fallback-testdata."
                )
            )
        self.stdout.write(
            f"Email backend: {CONSOLE_BACKEND}. Berichten afgeleverd: {sent_count}."
        )
