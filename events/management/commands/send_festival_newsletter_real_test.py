from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from events.festival_newsletter import build_festival_newsletter_preview
from events.mailers import (
    NewsletterEmailConfigError,
    NewsletterEmailProviderError,
    send_resend_newsletter_test,
)


class Command(BaseCommand):
    help = (
        "Send one explicit festival newsletter test email through Resend. "
        "This never sends bulk email."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="to_email",
            required=True,
            help="Explicit real test recipient address. Required; subscribers are never used.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of festival blocks to include, capped at 5.",
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

        preview = build_festival_newsletter_preview(limit=limit)
        if not preview.festivals:
            raise CommandError("Geen festivaldata beschikbaar voor de testmail.")

        try:
            result = send_resend_newsletter_test(
                to_email=to_email,
                subject=preview.subject,
                body=preview.body,
            )
        except (NewsletterEmailConfigError, NewsletterEmailProviderError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Echte festivalnieuwsbrief-testmail verstuurd naar {to_email} via Resend."
            )
        )
        if preview.uses_fallback_data:
            self.stdout.write(
                self.style.WARNING(
                    "Let op: deze testmail gebruikt gemarkeerde fallback-testdata."
                )
            )
        self.stdout.write(
            f"Provider: {result['provider']}. From: {result['from_email']}. Ontvangers: 1."
        )
