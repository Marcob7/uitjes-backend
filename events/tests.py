import csv
import json
import os
import tempfile
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from .models import Category, City, Event, Favorite, NewsletterSignup, Tag, Venue


class EventsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.city = City.objects.create(name="Apeldoorn", slug="apeldoorn")
        self.category, _ = Category.objects.get_or_create(
            slug="muziek",
            defaults={
                "name": "Muziek",
                "kind": Event.Kind.EVENT,
            },
        )
        self.venue = Venue.objects.create(
            name="Gigant",
            city=self.city,
            address="Nieuwstraat 1, Apeldoorn",
            latitude="52.211157",
            longitude="5.965546",
        )
        self.audience_tag, _ = Tag.objects.get_or_create(
            slug="vrienden",
            defaults={
                "name": "Vrienden",
                "facet": Tag.Facet.AUDIENCE,
            },
        )
        self.vibe_tag, _ = Tag.objects.get_or_create(
            slug="cultureel",
            defaults={
                "name": "Cultureel",
                "facet": Tag.Facet.VIBE,
            },
        )

        self.event = Event.objects.create(
            title="Live muziek in Gigant",
            slug="live-muziek-in-gigant-apeldoorn",
            city=self.city,
            venue=self.venue,
            category=self.category,
            summary="Een sterke avondmatch.",
            description="Volledige beschrijving",
            image_url="https://example.com/live-muziek.jpg",
            start_at=timezone.now() + timedelta(hours=2),
            is_free=False,
            price_min="18.00",
            date_text="Vanavond",
            raw_date_text="Vanavond",
            kind=Event.Kind.EVENT,
            is_featured=True,
        )
        self.active_event = Event.objects.create(
            title="Nu bezig in CODA",
            slug="nu-bezig-in-coda-apeldoorn",
            city=self.city,
            venue=self.venue,
            category=self.category,
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=1),
            date_text="Vandaag",
            raw_date_text="Vandaag",
            kind=Event.Kind.EVENT,
        )
        self.unknown_date_event = Event.objects.create(
            title="Datums volgen nog",
            slug="datums-volgen-nog-apeldoorn",
            city=self.city,
            date_text="Datum volgt",
            raw_date_text="Datum volgt",
            kind=Event.Kind.EVENT,
        )
        self.missing_date_event = Event.objects.create(
            title="Nog zonder datum",
            slug="nog-zonder-datum-apeldoorn",
            city=self.city,
            kind=Event.Kind.EVENT,
        )
        self.event.tags.add(self.audience_tag, self.vibe_tag)
        self.active_event.tags.add(self.audience_tag)

    def test_events_list_backwards_compatible_and_extended(self):
        response = self.client.get("/api/events/?city=apeldoorn&q=Live muziek")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn("count", payload)
        self.assertIn("results", payload)
        self.assertEqual(payload["count"], 1)

        result = payload["results"][0]
        self.assertEqual(result["id"], self.event.id)
        self.assertEqual(result["title"], self.event.title)
        self.assertEqual(result["city"], "apeldoorn")
        self.assertEqual(result["venue"], "Gigant")
        self.assertIn("summary", result)
        self.assertIn("slug", result)
        self.assertIn("category", result)
        self.assertIn("audiences", result)

    def test_event_detail_by_id_and_slug(self):
        response = self.client.get(f"/api/events/{self.event.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.event.id)

        slug_response = self.client.get(f"/api/events/by-slug/{self.event.slug}/")
        self.assertEqual(slug_response.status_code, 200)
        self.assertEqual(slug_response.json()["slug"], self.event.slug)

    def test_public_event_detail_hides_non_published_and_expired_records(self):
        hidden = Event.objects.create(
            title="Verborgen event",
            slug="verborgen-event",
            city=self.city,
            kind=Event.Kind.EVENT,
            status=Event.Status.HIDDEN,
        )
        expired = Event.objects.create(
            title="Afgelopen event",
            slug="afgelopen-event",
            city=self.city,
            kind=Event.Kind.EVENT,
            start_at=timezone.now() - timedelta(days=1),
        )

        hidden_response = self.client.get(f"/api/events/{hidden.id}/")
        expired_response = self.client.get(f"/api/events/by-slug/{expired.slug}/")

        self.assertEqual(hidden_response.status_code, 404)
        self.assertEqual(expired_response.status_code, 404)

    def test_metadata_endpoints(self):
        self.assertEqual(self.client.get("/api/cities/").status_code, 200)
        self.assertEqual(self.client.get("/api/cities/apeldoorn/").status_code, 200)
        self.assertEqual(self.client.get("/api/categories/").status_code, 200)
        self.assertEqual(self.client.get("/api/tags/").status_code, 200)

    def test_new_filters(self):
        response = self.client.get(
            "/api/events/?city=apeldoorn&category=muziek&audience=vrienden&vibe=cultureel&featured=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_ongoing_flag_and_filter_use_real_time_window(self):
        active_detail = self.client.get(f"/api/events/{self.active_event.id}/")
        self.assertEqual(active_detail.status_code, 200)
        self.assertTrue(active_detail.json()["is_ongoing"])
        self.assertEqual(active_detail.json()["status"], "Nu bezig")

        unknown_date_detail = self.client.get(f"/api/events/{self.unknown_date_event.id}/")
        self.assertEqual(unknown_date_detail.status_code, 200)
        self.assertFalse(unknown_date_detail.json()["is_ongoing"])
        self.assertEqual(unknown_date_detail.json()["status"], "Datum volgt")

        missing_date_detail = self.client.get(f"/api/events/{self.missing_date_event.id}/")
        self.assertEqual(missing_date_detail.status_code, 200)
        self.assertFalse(missing_date_detail.json()["is_ongoing"])
        self.assertEqual(missing_date_detail.json()["status"], "Datum nog te controleren")

        ongoing_response = self.client.get("/api/events/?city=apeldoorn&ongoing=1")
        self.assertEqual(ongoing_response.status_code, 200)
        self.assertEqual(ongoing_response.json()["count"], 1)
        self.assertEqual(ongoing_response.json()["results"][0]["id"], self.active_event.id)

        not_ongoing_response = self.client.get("/api/events/?city=apeldoorn&ongoing=0")
        self.assertEqual(not_ongoing_response.status_code, 200)
        returned_ids = {item["id"] for item in not_ongoing_response.json()["results"]}
        self.assertIn(self.event.id, returned_ids)
        self.assertIn(self.unknown_date_event.id, returned_ids)
        self.assertIn(self.missing_date_event.id, returned_ids)
        self.assertNotIn(self.active_event.id, returned_ids)

    def test_events_data_quality_endpoint_returns_counts_and_incomplete_records(self):
        response = self.client.get("/api/data-quality/events/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["total_events"], 4)
        self.assertEqual(payload["events_per_city"], {"apeldoorn": 4})
        self.assertEqual(payload["with_category"], 2)
        self.assertEqual(payload["without_category"], 2)
        self.assertEqual(payload["with_summary"], 1)
        self.assertEqual(payload["without_summary"], 3)
        self.assertEqual(payload["with_image_url"], 1)
        self.assertEqual(payload["without_image_url"], 3)
        self.assertEqual(payload["with_coordinates"], 2)
        self.assertEqual(payload["without_coordinates"], 2)
        self.assertEqual(payload["with_venue"], 2)
        self.assertEqual(payload["without_venue"], 2)
        self.assertEqual(payload["with_start_at"], 2)
        self.assertEqual(payload["without_start_at"], 2)
        self.assertEqual(payload["with_tags"], 2)
        self.assertEqual(payload["without_tags"], 2)
        self.assertEqual(payload["featured"], 1)
        self.assertEqual(payload["hidden_gem"], 0)
        self.assertEqual(payload["discover_ready"], 1)
        self.assertEqual(payload["not_discover_ready"], 3)

        incomplete_by_id = {item["id"]: item for item in payload["incomplete_records"]}
        self.assertEqual(len(incomplete_by_id), 3)
        self.assertFalse(incomplete_by_id[self.active_event.id]["discover_ready"])
        self.assertIn("summary", incomplete_by_id[self.active_event.id]["missing_fields"])
        self.assertIn("image_url", incomplete_by_id[self.unknown_date_event.id]["missing_fields"])

    def test_events_data_quality_endpoint_supports_city_filter(self):
        other_city = City.objects.create(name="Deventer", slug="deventer")
        Event.objects.create(
            title="Deventer compleet",
            city=other_city,
            category=self.category,
            summary="Compleet genoeg voor ontdek.",
            image_url="https://example.com/deventer.jpg",
            address="Brink 1, Deventer",
            date_text="Vandaag",
            is_hidden_gem=True,
        )

        response = self.client.get("/api/data-quality/events/?city=deventer")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["total_events"], 1)
        self.assertEqual(payload["events_per_city"], {"deventer": 1})
        self.assertEqual(payload["discover_ready"], 1)
        self.assertEqual(payload["not_discover_ready"], 0)
        self.assertEqual(payload["hidden_gem"], 1)
        self.assertEqual(payload["incomplete_records"], [])


class NewsletterSignupApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_valid_signup_creates_record_without_auth(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {"email": "Tester@Example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(NewsletterSignup.objects.count(), 1)

        signup = NewsletterSignup.objects.get()
        self.assertEqual(signup.email, "tester@example.com")
        self.assertEqual(signup.frequency, NewsletterSignup.Frequency.WEEKLY)
        self.assertEqual(signup.interests, [])
        self.assertTrue(signup.is_active)

    def test_invalid_email_returns_neat_error(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {"email": "geen-email"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("geldig e-mailadres", response.json()["message"])
        self.assertEqual(NewsletterSignup.objects.count(), 0)

    def test_empty_email_returns_neat_error(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {"email": ""},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(NewsletterSignup.objects.count(), 0)

    def test_duplicate_email_reactivates_existing_signup(self):
        signup = NewsletterSignup.objects.create(
            email="tester@example.com",
            preferred_city="Zwolle",
            source="footer",
            frequency=NewsletterSignup.Frequency.MONTHLY,
            interests=["family"],
            is_active=False,
            unsubscribed_at=timezone.now(),
        )

        response = self.client.post(
            "/api/newsletter/signup/",
            {
                "email": "TESTER@example.com",
                "city": "Apeldoorn",
                "frequency": "weekend",
                "interests": ["festivals", "food_drink"],
                "source": "homepage",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIn("al aangemeld", response.json()["message"])
        self.assertEqual(NewsletterSignup.objects.count(), 1)

        signup.refresh_from_db()
        self.assertEqual(signup.email, "tester@example.com")
        self.assertEqual(signup.preferred_city, "Apeldoorn")
        self.assertEqual(signup.frequency, NewsletterSignup.Frequency.WEEKEND)
        self.assertEqual(signup.interests, ["festivals", "food_drink"])
        self.assertEqual(signup.source, "homepage")
        self.assertTrue(signup.is_active)
        self.assertIsNone(signup.unsubscribed_at)

    def test_optional_city_source_and_preferences_are_stored(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {
                "email": "stad@example.com",
                "preferred_city": "Harderwijk",
                "frequency": "monthly",
                "interests": ["events", "family", "events"],
                "source": "inspiration",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        signup = NewsletterSignup.objects.get(email="stad@example.com")
        self.assertEqual(signup.preferred_city, "Harderwijk")
        self.assertEqual(signup.frequency, NewsletterSignup.Frequency.MONTHLY)
        self.assertEqual(signup.interests, ["events", "family"])
        self.assertEqual(signup.source, "inspiration")

    def test_invalid_frequency_returns_neat_error(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {
                "email": "stad@example.com",
                "frequency": "daily",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("frequency", response.json()["errors"])
        self.assertEqual(NewsletterSignup.objects.count(), 0)

    def test_invalid_interest_returns_neat_error(self):
        response = self.client.post(
            "/api/newsletter/signup/",
            {
                "email": "stad@example.com",
                "interests": ["festivals", "unknown"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("interests", response.json()["errors"])
        self.assertEqual(NewsletterSignup.objects.count(), 0)


class FestivalNewsletterTestMailCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Apeldoorn", slug="apeldoorn")
        self.category, _ = Category.objects.get_or_create(
            slug="festival",
            defaults={
                "name": "Festival",
                "kind": Event.Kind.FESTIVAL,
            },
        )
        self.venue = Venue.objects.create(
            name="Stadspark",
            city=self.city,
            address="Parklaan 1",
        )

    def test_command_requires_explicit_to_address(self):
        with self.assertRaises(CommandError):
            call_command("send_festival_newsletter_test")

    def test_command_with_to_uses_console_backend_and_outputs_mail(self):
        Event.objects.create(
            title="Apeldoorn Zomerfestival",
            slug="apeldoorn-zomerfestival",
            kind=Event.Kind.FESTIVAL,
            city=self.city,
            venue=self.venue,
            category=self.category,
            summary="Muziek, eten en cultuur in het stadspark.",
            date_text="12 juli 2026",
            ticket_url="https://example.com/tickets",
        )
        out = StringIO()

        call_command(
            "send_festival_newsletter_test",
            to_email="test@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Subject: Festival tips voor je volgende uitje", output)
        self.assertIn("To: test@example.com", output)
        self.assertIn("Apeldoorn Zomerfestival", output)
        self.assertIn("12 juli 2026", output)
        self.assertIn("Stadspark, Apeldoorn", output)
        self.assertIn("https://example.com/tickets", output)
        self.assertIn("django.core.mail.backends.console.EmailBackend", output)

    def test_command_does_not_send_to_newsletter_signups(self):
        NewsletterSignup.objects.create(email="subscriber@example.com")
        out = StringIO()

        call_command(
            "send_festival_newsletter_test",
            to_email="test@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("To: test@example.com", output)
        self.assertNotIn("subscriber@example.com", output)

    def test_command_fallback_body_has_no_placeholder_values(self):
        out = StringIO()

        call_command(
            "send_festival_newsletter_test",
            to_email="test@example.com",
            limit=3,
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("fallback-testdata", output)
        self.assertIn("Dekmantel Festival", output)
        for placeholder in ("undefined", "null", "nan"):
            self.assertNotIn(placeholder, output.lower())


class EventsNewsletterTestMailCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Apeldoorn", slug="apeldoorn")
        self.category, _ = Category.objects.get_or_create(
            slug="muziek-events",
            defaults={
                "name": "Muziek",
                "kind": Event.Kind.EVENT,
            },
        )
        self.venue = Venue.objects.create(
            name="Gigant",
            city=self.city,
            address="Nieuwstraat 1",
        )

    def test_command_requires_explicit_to_address(self):
        with self.assertRaises(CommandError):
            call_command("send_events_newsletter_test")

    def test_command_with_to_uses_console_backend_and_outputs_event_mail(self):
        Event.objects.create(
            title="Live muziek in Gigant",
            slug="live-muziek-in-gigant",
            kind=Event.Kind.EVENT,
            city=self.city,
            venue=self.venue,
            category=self.category,
            summary="Een avond met lokale bands.",
            date_text="14 juni 2026",
            source_url="https://example.com/live-muziek",
        )
        out = StringIO()

        call_command(
            "send_events_newsletter_test",
            to_email="test@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Subject: Evenemententips voor je volgende uitje", output)
        self.assertIn("To: test@example.com", output)
        self.assertIn("Live muziek in Gigant", output)
        self.assertIn("14 juni 2026", output)
        self.assertIn("Gigant, Apeldoorn", output)
        self.assertIn("Een avond met lokale bands.", output)
        self.assertIn("https://example.com/live-muziek", output)
        self.assertIn("django.core.mail.backends.console.EmailBackend", output)

    def test_command_does_not_send_to_newsletter_signups(self):
        NewsletterSignup.objects.create(email="subscriber@example.com")
        out = StringIO()

        call_command(
            "send_events_newsletter_test",
            to_email="test@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("To: test@example.com", output)
        self.assertNotIn("subscriber@example.com", output)

    def test_command_does_not_use_food_drink_as_event_newsletter_content(self):
        Event.objects.create(
            title="Lunch aan de haven",
            slug="lunch-aan-de-haven",
            kind=Event.Kind.FOOD_DRINK,
            city=self.city,
            summary="Restaurant met terras.",
            date_text="Elke dag",
        )
        out = StringIO()

        call_command(
            "send_events_newsletter_test",
            to_email="test@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertNotIn("Lunch aan de haven", output)
        self.assertIn("fallback-testdata", output)

    def test_command_body_has_no_placeholder_values(self):
        Event.objects.create(
            title="undefined",
            slug="placeholder-event",
            kind=Event.Kind.EVENT,
            city=self.city,
            summary="null",
            description="nan",
            date_text="n/a",
            raw_date_text="none",
            ticket_url="undefined",
            source_url="nan",
        )
        out = StringIO()

        call_command(
            "send_events_newsletter_test",
            to_email="test@example.com",
            limit=1,
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Evenemententip", output)
        for placeholder in ("undefined", "null", "nan"):
            self.assertNotIn(placeholder, output.lower())


class FestivalNewsletterRealTestMailCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Apeldoorn", slug="apeldoorn")
        self.category, _ = Category.objects.get_or_create(
            slug="festival-real",
            defaults={
                "name": "Festival",
                "kind": Event.Kind.FESTIVAL,
            },
        )
        self.venue = Venue.objects.create(
            name="Stadspark",
            city=self.city,
            address="Parklaan 1",
        )

    def test_command_requires_explicit_to_address(self):
        with self.assertRaises(CommandError):
            call_command("send_festival_newsletter_real_test")

    @override_settings(RESEND_API_KEY="")
    def test_missing_resend_api_key_returns_neat_error(self):
        with self.assertRaisesMessage(CommandError, "RESEND_API_KEY ontbreekt"):
            call_command(
                "send_festival_newsletter_real_test",
                to_email="test@example.com",
            )

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_missing_from_email_returns_neat_error(self):
        with self.assertRaisesMessage(CommandError, "RESEND_FROM_EMAIL of DEFAULT_FROM_EMAIL ontbreekt"):
            call_command(
                "send_festival_newsletter_real_test",
                to_email="test@example.com",
            )

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="Uitjes <newsletter@example.com>",
    )
    @patch("events.mailers.import_module")
    def test_success_path_sends_one_explicit_resend_email(self, import_module_mock):
        Event.objects.create(
            title="Apeldoorn Zomerfestival",
            slug="apeldoorn-zomerfestival-real",
            kind=Event.Kind.FESTIVAL,
            city=self.city,
            venue=self.venue,
            category=self.category,
            summary="Muziek, eten en cultuur in het stadspark.",
            date_text="12 juli 2026",
            ticket_url="https://example.com/tickets",
        )
        NewsletterSignup.objects.create(email="subscriber@example.com")
        resend = Mock()
        resend.Emails.send.return_value = {"id": "email_123"}
        import_module_mock.return_value = resend
        out = StringIO()

        call_command(
            "send_festival_newsletter_real_test",
            to_email="test@example.com",
            stdout=out,
        )

        params = resend.Emails.send.call_args.args[0]
        self.assertEqual(params["from"], "Uitjes <newsletter@example.com>")
        self.assertEqual(params["to"], ["test@example.com"])
        self.assertEqual(params["subject"], "Festival tips voor je volgende uitje")
        self.assertIn("Apeldoorn Zomerfestival", params["text"])
        self.assertIn("12 juli 2026", params["text"])
        self.assertIn("Muziek, eten en cultuur", params["text"])
        self.assertIn("[TESTMAIL - VERZONDEN VIA RESEND]", params["text"])
        self.assertIn("echte testmail, verzonden via Resend", params["text"])
        self.assertIn(
            "Er is nog geen bulkverzending naar nieuwsbriefinschrijvers actief.",
            params["text"],
        )
        self.assertNotIn("[LOKALE TESTMAIL - GEEN ECHTE VERZENDING]", params["text"])
        self.assertNotIn("Er is nog geen echte mailprovider gekoppeld", params["text"])
        self.assertNotIn("subscriber@example.com", str(params))
        for placeholder in ("undefined", "null", "nan"):
            self.assertNotIn(placeholder, params["text"].lower())
        self.assertIn("via Resend", out.getvalue())
        self.assertIn("Ontvangers: 1", out.getvalue())

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="Uitjes <newsletter@example.com>",
    )
    @patch("events.mailers.import_module")
    def test_provider_failure_returns_neat_error(self, import_module_mock):
        resend = Mock()
        resend.Emails.send.side_effect = RuntimeError("provider offline")
        import_module_mock.return_value = resend

        with self.assertRaisesMessage(CommandError, "Resend kon de testmail niet versturen"):
            call_command(
                "send_festival_newsletter_real_test",
                to_email="test@example.com",
            )


class EventsNewsletterRealTestMailCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Apeldoorn", slug="apeldoorn")
        self.category, _ = Category.objects.get_or_create(
            slug="muziek-events-real",
            defaults={
                "name": "Muziek",
                "kind": Event.Kind.EVENT,
            },
        )
        self.venue = Venue.objects.create(
            name="Gigant",
            city=self.city,
            address="Nieuwstraat 1",
        )

    def test_command_requires_explicit_to_address(self):
        with self.assertRaises(CommandError):
            call_command("send_events_newsletter_real_test")

    @override_settings(RESEND_API_KEY="")
    def test_missing_resend_api_key_returns_neat_error(self):
        with self.assertRaisesMessage(CommandError, "RESEND_API_KEY ontbreekt"):
            call_command(
                "send_events_newsletter_real_test",
                to_email="test@example.com",
            )

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_missing_from_email_returns_neat_error(self):
        with self.assertRaisesMessage(CommandError, "RESEND_FROM_EMAIL of DEFAULT_FROM_EMAIL ontbreekt"):
            call_command(
                "send_events_newsletter_real_test",
                to_email="test@example.com",
            )

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="",
        DEFAULT_FROM_EMAIL="Uitjes <default@example.com>",
    )
    @patch("events.mailers.import_module")
    def test_uses_default_from_email_when_resend_from_email_is_empty(self, import_module_mock):
        resend = Mock()
        resend.Emails.send.return_value = {"id": "email_default"}
        import_module_mock.return_value = resend

        call_command(
            "send_events_newsletter_real_test",
            to_email="test@example.com",
        )

        params = resend.Emails.send.call_args.args[0]
        self.assertEqual(params["from"], "Uitjes <default@example.com>")

    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_FROM_EMAIL="Uitjes <newsletter@example.com>",
    )
    @patch("events.mailers.import_module")
    def test_success_path_sends_one_explicit_resend_email(self, import_module_mock):
        Event.objects.create(
            title="Live muziek in Gigant",
            slug="live-muziek-in-gigant-real",
            kind=Event.Kind.EVENT,
            city=self.city,
            venue=self.venue,
            category=self.category,
            summary="Een avond met lokale bands.",
            date_text="14 juni 2026",
            source_url="https://example.com/live-muziek",
        )
        NewsletterSignup.objects.create(email="subscriber@example.com")
        resend = Mock()
        resend.Emails.send.return_value = {"id": "email_456"}
        import_module_mock.return_value = resend
        out = StringIO()

        call_command(
            "send_events_newsletter_real_test",
            to_email="test@example.com",
            stdout=out,
        )

        params = resend.Emails.send.call_args.args[0]
        self.assertEqual(params["from"], "Uitjes <newsletter@example.com>")
        self.assertEqual(params["to"], ["test@example.com"])
        self.assertEqual(params["subject"], "Evenemententips voor je volgende uitje")
        self.assertIn("Live muziek in Gigant", params["text"])
        self.assertIn("14 juni 2026", params["text"])
        self.assertIn("Een avond met lokale bands.", params["text"])
        self.assertIn("[TESTMAIL - VERZONDEN VIA RESEND]", params["text"])
        self.assertIn("echte testmail, verzonden via Resend", params["text"])
        self.assertIn(
            "Er is nog geen bulkverzending naar nieuwsbriefinschrijvers actief.",
            params["text"],
        )
        self.assertNotIn("[LOKALE TESTMAIL - GEEN ECHTE VERZENDING]", params["text"])
        self.assertNotIn("Er is nog geen echte mailprovider gekoppeld", params["text"])
        self.assertNotIn("subscriber@example.com", str(params))
        for placeholder in ("undefined", "null", "nan"):
            self.assertNotIn(placeholder, params["text"].lower())
        self.assertIn("via Resend", out.getvalue())
        self.assertIn("Ontvangers: 1", out.getvalue())


class CityContentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.city = City.objects.create(name="Harderwijk", slug="harderwijk")
        self.lelystad = City.objects.create(name="Lelystad", slug="lelystad")
        self.other_city = City.objects.create(name="Deventer", slug="deventer")
        self.activity_category, _ = Category.objects.get_or_create(
            slug="activiteit",
            defaults={
                "name": "Activiteit",
                "kind": Event.Kind.ACTIVITY,
            },
        )
        self.food_category, _ = Category.objects.get_or_create(
            slug="restaurant",
            defaults={
                "name": "Restaurant",
                "kind": Event.Kind.FOOD_DRINK,
            },
        )
        self.venue = Venue.objects.create(
            name="Museum Harderwijk",
            slug="museum-harderwijk",
            city=self.city,
            address="Markt 1",
            latitude="52.350000",
            longitude="5.620000",
        )
        self.tag = Tag.objects.create(
            name="Gezinnen",
            slug="gezinnen",
            facet=Tag.Facet.AUDIENCE,
        )
        self.outing = Event.objects.create(
            title="Museumwandeling Harderwijk",
            slug="museumwandeling-harderwijk",
            kind=Event.Kind.ACTIVITY,
            city=self.city,
            venue=self.venue,
            category=self.activity_category,
            summary="Een wandeling langs het museum.",
            description="Route door de stad met museumstop.",
            source_url="https://example.com/museumwandeling",
            ticket_url="nan",
            image_url="NaN",
            price_note="",
            rating_value="4.60",
            review_count=128,
            rating_source="Google",
            rating_max="5.00",
            rating_url="https://example.com/museumwandeling/reviews",
            rating_last_checked_at="2026-05-29",
        )
        self.outing.tags.add(self.tag)
        self.food = Event.objects.create(
            title="Lunch aan de haven",
            slug="lunch-aan-de-haven",
            kind=Event.Kind.FOOD_DRINK,
            city=self.city,
            category=self.food_category,
            summary="Lunchplek aan de haven.",
            description="Restaurant met terras.",
            address="Havenkade 2",
            latitude="52.351000",
            longitude="5.621000",
            source_url="https://example.com/lunch-aan-de-haven",
            price_note="n/a",
        )
        Event.objects.create(
            title="Deventer wandeling",
            slug="deventer-wandeling",
            kind=Event.Kind.ACTIVITY,
            city=self.other_city,
            category=self.activity_category,
            source_url="https://example.com/deventer-wandeling",
        )
        self.lelystad_outing = Event.objects.create(
            title="Lelystad stadswandeling",
            slug="lelystad-stadswandeling",
            kind=Event.Kind.ACTIVITY,
            city=self.lelystad,
            category=self.activity_category,
            source="city_content:outings",
            source_url="https://example.com/lelystad-stadswandeling",
        )
        self.lelystad_food = Event.objects.create(
            title="Lelystad restaurant",
            slug="lelystad-restaurant",
            kind=Event.Kind.FOOD_DRINK,
            city=self.lelystad,
            category=self.food_category,
            source="city_content:food_drink",
            source_url="https://example.com/lelystad-restaurant",
        )
        for title, slug, kind in [
            ("Lelystad snackbar", "lelystad-snackbar", "snackbar"),
            ("Lelystad ijssalon", "lelystad-ijssalon", "ice_cream"),
            ("Lelystad strandpaviljoen", "lelystad-strandpaviljoen", "beach_pavilion"),
        ]:
            Event.objects.create(
                title=title,
                slug=slug,
                kind=kind,
                city=self.lelystad,
                category=self.food_category,
                source="city_content:food_drink",
                source_url=f"https://example.com/{slug}",
            )
        Event.objects.create(
            title="Lelystad food paviljoen",
            slug="lelystad-food-paviljoen",
            kind=Event.Kind.PLACE,
            city=self.lelystad,
            category=self.food_category,
            source="city_content:food_drink",
            source_url="https://example.com/lelystad-food-paviljoen",
        )
        Event.objects.create(
            title="Lelystad gewoon park",
            slug="lelystad-gewoon-park",
            kind=Event.Kind.PLACE,
            city=self.lelystad,
            category=self.activity_category,
            source="city_content:outings",
            source_url="https://example.com/lelystad-gewoon-park",
        )

    def test_city_content_endpoint_returns_200(self):
        response = self.client.get("/api/city-content/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_city_filter_returns_only_requested_city(self):
        response = self.client.get("/api/city-content/?city=harderwijk")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual({item["city"] for item in payload["results"]}, {"harderwijk"})

    def test_type_food_drink_returns_food_drink(self):
        response = self.client.get("/api/city-content/?city=harderwijk&type=food_drink")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["kind"], Event.Kind.FOOD_DRINK)

    def test_type_outings_excludes_food_drink(self):
        response = self.client.get("/api/city-content/?city=harderwijk&type=outings")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        returned_kinds = {item["kind"] for item in payload["results"]}
        self.assertNotIn(Event.Kind.FOOD_DRINK, returned_kinds)

    def test_type_food_drink_includes_food_drink_subtypes(self):
        response = self.client.get("/api/city-content/?city=lelystad&type=food_drink&limit=20")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 5)
        returned_kinds = {item["kind"] for item in payload["results"]}
        self.assertEqual(
            returned_kinds,
            {
                Event.Kind.FOOD_DRINK,
                "snackbar",
                "ice_cream",
                "beach_pavilion",
                Event.Kind.PLACE,
            },
        )

    def test_type_outings_excludes_food_drink_subtypes(self):
        response = self.client.get("/api/city-content/?city=lelystad&type=outings&limit=20")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 2)
        returned_slugs = {item["slug"] for item in payload["results"]}
        self.assertEqual(returned_slugs, {"lelystad-stadswandeling", "lelystad-gewoon-park"})

    def test_harderwijk_counts_remain_unchanged_with_food_drink_mapping(self):
        food_response = self.client.get("/api/city-content/?city=harderwijk&type=food_drink")
        outings_response = self.client.get("/api/city-content/?city=harderwijk&type=outings")

        self.assertEqual(food_response.status_code, 200)
        self.assertEqual(outings_response.status_code, 200)
        self.assertEqual(food_response.json()["count"], 1)
        self.assertEqual(outings_response.json()["count"], 1)

    def test_query_filter_searches_without_crashing(self):
        response = self.client.get("/api/city-content/?city=harderwijk&query=museum")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["slug"], self.outing.slug)

    def test_nan_like_values_are_serialized_as_null(self):
        response = self.client.get("/api/city-content/?city=harderwijk&type=outings")
        self.assertEqual(response.status_code, 200)

        item = response.json()["results"][0]
        self.assertIsNone(item["ticket_url"])
        self.assertIsNone(item["image_url"])
        self.assertIsNone(item["price_note"])
        self.assertNotIn('"nan"', json.dumps(response.json()).lower())

    def test_city_content_response_includes_public_review_fields(self):
        response = self.client.get("/api/city-content/?city=harderwijk&type=outings")
        self.assertEqual(response.status_code, 200)

        item = response.json()["results"][0]
        self.assertEqual(item["rating_value"], "4.60")
        self.assertEqual(item["review_count"], 128)
        self.assertEqual(item["rating_source"], "Google")
        self.assertEqual(item["rating_max"], "5.00")
        self.assertEqual(item["rating_url"], "https://example.com/museumwandeling/reviews")
        self.assertEqual(item["rating_last_checked_at"], "2026-05-29")

    def test_city_content_only_returns_published_records(self):
        hidden = Event.objects.create(
            title="Verborgen wandeling",
            slug="verborgen-wandeling",
            kind=Event.Kind.ACTIVITY,
            city=self.city,
            category=self.activity_category,
            status=Event.Status.HIDDEN,
        )
        archived = Event.objects.create(
            title="Gearchiveerde wandeling",
            slug="gearchiveerde-wandeling",
            kind=Event.Kind.ACTIVITY,
            city=self.city,
            category=self.activity_category,
            status=Event.Status.ARCHIVED,
        )

        response = self.client.get("/api/city-content/?city=harderwijk&type=outings&limit=20")
        self.assertEqual(response.status_code, 200)

        returned_ids = {item["id"] for item in response.json()["results"]}
        self.assertNotIn(hidden.id, returned_ids)
        self.assertNotIn(archived.id, returned_ids)

    def test_city_content_filters_expired_events_without_hiding_places(self):
        expired_event = Event.objects.create(
            title="Afgelopen voorstelling",
            slug="afgelopen-voorstelling",
            kind=Event.Kind.EVENT,
            city=self.city,
            category=self.activity_category,
            start_at=timezone.now() - timedelta(days=2),
        )
        old_place = Event.objects.create(
            title="Historisch plein",
            slug="historisch-plein",
            kind=Event.Kind.PLACE,
            city=self.city,
            category=self.activity_category,
            start_at=timezone.now() - timedelta(days=365),
        )

        response = self.client.get("/api/city-content/?city=harderwijk&type=outings&limit=20")
        self.assertEqual(response.status_code, 200)

        returned_ids = {item["id"] for item in response.json()["results"]}
        self.assertNotIn(expired_event.id, returned_ids)
        self.assertIn(old_place.id, returned_ids)


class EventLifecycleCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Harderwijk", slug="harderwijk")
        self.other_city = City.objects.create(name="Lelystad", slug="lelystad")

    def test_check_event_lifecycle_reports_without_modifying_records(self):
        expired = Event.objects.create(
            title="Afgelopen festival",
            slug="dubbele-slug",
            kind=Event.Kind.FESTIVAL,
            city=self.city,
            start_at=timezone.now() - timedelta(days=3),
        )
        Event.objects.create(
            title="Tweede met dubbele slug",
            slug="dubbele-slug",
            kind=Event.Kind.ACTIVITY,
            city=self.city,
            status=Event.Status.HIDDEN,
        )
        Event.objects.create(
            title="Datum ontbreekt",
            slug="datum-ontbreekt",
            kind=Event.Kind.ACTIVITY,
            city=self.other_city,
            status=Event.Status.NEEDS_REVIEW,
        )
        Event.objects.create(
            title="Gearchiveerd item",
            slug="gearchiveerd-item",
            kind=Event.Kind.ACTIVITY,
            city=self.other_city,
            status=Event.Status.ARCHIVED,
            date_text="Doorlopend",
        )

        before = list(Event.objects.order_by("id").values_list("id", "status"))
        out = StringIO()
        call_command("check_event_lifecycle", stdout=out)
        after = list(Event.objects.order_by("id").values_list("id", "status"))

        output = out.getvalue()
        self.assertEqual(after, before)
        self.assertIn("Verlopen event-kandidaten: 1", output)
        self.assertIn(f"#{expired.id}", output)
        self.assertIn("Records zonder duidelijke datum mogelijk needs_review: 2", output)
        self.assertIn("harderwijk: hidden=1", output)
        self.assertIn("lelystad: archived=1", output)
        self.assertIn("dubbele-slug (2 records)", output)


class FavoritesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="tester",
            email="tester@example.com",
            password="secret123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password="secret123",
        )
        self.city = City.objects.create(name="Deventer", slug="deventer")
        self.category, _ = Category.objects.get_or_create(
            slug="festival",
            defaults={
                "name": "Festival",
                "kind": Event.Kind.FESTIVAL,
            },
        )
        self.event = Event.objects.create(
            title="Food Festival Deventer",
            slug="food-festival-deventer",
            city=self.city,
            category=self.category,
            summary="Lekker eten aan de IJssel.",
            image_url="https://example.com/food.jpg",
            kind=Event.Kind.FESTIVAL,
        )
        self.other_event = Event.objects.create(
            title="Andere wandeling",
            slug="andere-wandeling",
            city=self.city,
            kind=Event.Kind.ACTIVITY,
        )

    def test_unauthenticated_user_cannot_read_favorites(self):
        response = self.client.get("/api/favorites/")

        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_user_can_add_favorite(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/favorites/",
            {"event_id": self.event.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Favorite.objects.count(), 1)
        payload = response.json()
        self.assertEqual(payload["event_id"], self.event.id)
        self.assertEqual(payload["title"], self.event.title)
        self.assertEqual(payload["slug"], self.event.slug)
        self.assertEqual(payload["city"], self.city.slug)
        self.assertEqual(payload["kind"], Event.Kind.FESTIVAL)
        self.assertEqual(payload["category"], self.category.name)
        self.assertEqual(payload["summary"], self.event.summary)
        self.assertEqual(payload["image_url"], self.event.image_url)

    def test_duplicate_favorite_does_not_create_duplicate_record(self):
        self.client.force_authenticate(self.user)

        first_response = self.client.post(
            "/api/favorites/",
            {"event_id": self.event.id},
            format="json",
        )
        second_response = self.client.post(
            "/api/favorites/",
            {"event_id": self.event.id},
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Favorite.objects.filter(user=self.user, event=self.event).count(), 1)

    def test_authenticated_user_can_remove_favorite_without_deleting_event(self):
        self.client.force_authenticate(self.user)
        Favorite.objects.create(user=self.user, event=self.event)

        response = self.client.delete(f"/api/favorites/{self.event.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Favorite.objects.filter(user=self.user, event=self.event).exists())
        self.assertTrue(Event.objects.filter(id=self.event.id).exists())

    def test_user_only_sees_own_favorites(self):
        Favorite.objects.create(user=self.user, event=self.event)
        Favorite.objects.create(user=self.other_user, event=self.other_event)
        self.client.force_authenticate(self.user)

        list_response = self.client.get("/api/favorites/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["event_id"] for item in list_response.json()], [self.event.id])

    def test_user_cannot_remove_other_users_favorite(self):
        Favorite.objects.create(user=self.other_user, event=self.event)
        self.client.force_authenticate(self.user)

        response = self.client.delete(f"/api/favorites/{self.event.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertTrue(Favorite.objects.filter(user=self.other_user, event=self.event).exists())

    def test_jwt_authentication_works_with_favorites_endpoints(self):
        login_response = self.client.post(
            "/api/auth/token/",
            {
                "username": "tester",
                "password": "secret123",
            },
            format="json",
        )
        access = login_response.json()["access"]

        add_response = self.client.post(
            "/api/favorites/",
            {"event_id": self.event.id},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        list_response = self.client.get(
            "/api/favorites/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )

        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["event_id"], self.event.id)

    def test_compatibility_favorites_events_endpoint_still_returns_events(self):
        Favorite.objects.create(user=self.user, event=self.event)
        self.client.force_authenticate(self.user)

        events_response = self.client.get("/api/favorites/events/")
        self.assertEqual(events_response.status_code, 200)
        self.assertEqual(events_response.json()[0]["id"], self.event.id)


class JwtAuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="jwt-user",
            email="jwt-user@example.com",
            password="correct-password-123",
            first_name="Jwt",
            last_name="Tester",
        )

    def test_valid_login_with_username_returns_tokens(self):
        response = self.client.post(
            "/api/auth/token/",
            {
                "username": "jwt-user",
                "password": "correct-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)

    def test_valid_login_with_email_returns_tokens(self):
        response = self.client.post(
            "/api/auth/token/",
            {
                "email": "jwt-user@example.com",
                "password": "correct-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_invalid_login_fails_cleanly(self):
        response = self.client.post(
            "/api/auth/token/",
            {
                "username": "jwt-user",
                "password": "wrong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_refresh_endpoint_returns_new_access_token(self):
        login_response = self.client.post(
            "/api/auth/token/",
            {
                "username": "jwt-user",
                "password": "correct-password-123",
            },
            format="json",
        )
        refresh = login_response.json()["refresh"]

        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_auth_me_without_token_fails_cleanly(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_auth_me_with_valid_jwt_returns_user(self):
        login_response = self.client.post(
            "/api/auth/token/",
            {
                "username": "jwt-user",
                "password": "correct-password-123",
            },
            format="json",
        )
        access = login_response.json()["access"]

        response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": self.user.id,
            "username": "jwt-user",
            "email": "jwt-user@example.com",
            "first_name": "Jwt",
            "last_name": "Tester",
            "is_authenticated": True,
        })


class ImportCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Zwolle", slug="zwolle")

    def _create_excel_file(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "Naam/Activiteit",
            "Type",
            "Datum",
            "Omschrijving",
            "Website",
            "Category",
            "AudienceTags",
        ])
        sheet.append([
            "Zwolle Test Event",
            "Nieuw",
            "1 januari 2026",
            "Test omschrijving",
            "https://example.com/zwolle-test-event",
            "Cultuur",
            "Solo,Vrienden",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def _create_dry_run_excel_file(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "Naam/Activiteit",
            "Kind",
            "Datum",
            "Omschrijving",
            "Website",
            "SourceId",
            "Category",
            "Latitude",
            "Longitude",
            "IndoorOutdoor",
            "WeatherSuitability",
            "Gratis",
        ])
        sheet.append([
            "Bestaand Zwolle Event",
            "event",
            "1 januari 2026",
            "Zou update zijn",
            "https://example.com/existing-zwolle-event",
            "existing-1",
            "Cultuur",
            "52.512",
            "6.094",
            "indoor",
            "rain",
            "ja",
        ])
        sheet.append([
            "Nieuw Zwolle Event",
            "festival",
            "2 januari 2026",
            "Zou create zijn",
            "https://example.com/new-zwolle-event",
            "new-1",
            "Festival",
            "52.513",
            "6.095",
            "outdoor",
            "sun",
            "nee",
        ])
        sheet.append([
            "",
            "event",
            "3 januari 2026",
            "Mist titel",
            "https://example.com/missing-title",
            "missing-title",
            "Cultuur",
            "52.514",
            "6.096",
            "indoor",
            "all",
            "true",
        ])
        sheet.append([
            "Ongeldige waarden",
            "mystery",
            "32 januari 2026",
            "Heeft warnings",
            "https://example.com/invalid-values",
            "invalid-1",
            "Cultuur",
            "noord",
            "oost",
            "inside",
            "storm",
            "misschien",
        ])
        sheet.append([
            "Duplicate source",
            "event",
            "4 januari 2026",
            "Dubbele SourceId",
            "https://example.com/duplicate-source",
            "new-1",
            "Cultuur",
            "52.515",
            "6.097",
            "indoor",
            "all",
            "yes",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def test_import_command_is_idempotent(self):
        path = self._create_excel_file()
        try:
            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
            )
            first_event = Event.objects.get(source_url="https://example.com/zwolle-test-event")
            first_id = first_event.id

            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
            )

            self.assertEqual(
                Event.objects.filter(source_url="https://example.com/zwolle-test-event").count(),
                1,
            )
            self.assertEqual(
                Event.objects.get(source_url="https://example.com/zwolle-test-event").id,
                first_id,
            )
            self.assertEqual(Event.objects.get(id=first_id).raw_date_text, "1 januari 2026")
        finally:
            if os.path.exists(path):
                os.unlink(path)


    def test_import_command_dry_run_does_not_change_database(self):
        Event.objects.create(
            title="Bestaand Zwolle Event",
            city=self.city,
            source_url="https://example.com/existing-zwolle-event",
            source="excel_zwolle_test",
        )
        before_counts = {
            "events": Event.objects.count(),
            "categories": Category.objects.count(),
            "tags": Tag.objects.count(),
            "venues": Venue.objects.count(),
        }
        path = self._create_dry_run_excel_file()
        stdout = StringIO()
        stderr = StringIO()

        try:
            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
                dry_run=True,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            if os.path.exists(path):
                os.unlink(path)

        self.assertEqual(Event.objects.count(), before_counts["events"])
        self.assertEqual(Category.objects.count(), before_counts["categories"])
        self.assertEqual(Tag.objects.count(), before_counts["tags"])
        self.assertEqual(Venue.objects.count(), before_counts["venues"])

        output = stdout.getvalue()
        self.assertIn("DRY RUN: no database changes were written.", output)
        self.assertIn("rows=5", output)
        self.assertIn("would_create=2", output)
        self.assertIn("would_update=1", output)
        self.assertIn("would_skip=2", output)
        self.assertIn("errors=0", output)
        self.assertIn("missing required field title", output)
        self.assertIn("invalid date '32 januari 2026'", output)
        self.assertIn("invalid latitude 'noord'", output)
        self.assertIn("invalid longitude 'oost'", output)
        self.assertIn("unknown Kind value 'mystery'", output)
        self.assertIn("unknown IndoorOutdoor value 'inside'", output)
        self.assertIn("unknown WeatherSuitability value 'storm'", output)
        self.assertIn("unknown boolean value 'misschien'", output)
        self.assertIn("duplicate SourceId or dedupe_key 'new-1'", output)

    def test_import_command_dry_run_writes_report_without_database_changes(self):
        existing_event = Event.objects.create(
            title="Bestaand Zwolle Event",
            city=self.city,
            source_url="https://example.com/existing-zwolle-event",
            source="excel_zwolle_test",
        )
        path = self._create_dry_run_excel_file()
        report_dir = tempfile.mkdtemp()
        report_path = os.path.join(report_dir, "nested", "dry_run_report.csv")
        before_event_count = Event.objects.count()

        try:
            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
                dry_run=True,
                report_file=report_path,
            )

            self.assertEqual(Event.objects.count(), before_event_count)
            self.assertTrue(os.path.exists(report_path))

            with open(report_path, newline="", encoding="utf-8") as report_file:
                rows = list(csv.DictReader(report_file))

            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0]["action"], "would_update")
            self.assertEqual(rows[0]["event_id"], str(existing_event.id))
            self.assertEqual(rows[0]["discover_ready"], "false")
            self.assertIn("summary", rows[0]["missing_recommended_fields"])
            self.assertEqual(rows[1]["action"], "would_create")
            self.assertEqual(rows[1]["source_id"], "new-1")
            self.assertEqual(rows[2]["action"], "would_skip")
            self.assertIn("missing required field title", rows[2]["warnings"])
            self.assertEqual(rows[3]["action"], "would_create")
            self.assertIn("unknown Kind value 'mystery'", rows[3]["warnings"])
            self.assertIn("invalid latitude 'noord'", rows[3]["warnings"])
            self.assertEqual(rows[4]["action"], "would_skip")
            self.assertIn("duplicate SourceId or dedupe_key 'new-1'", rows[4]["warnings"])
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_import_command_normal_import_writes_report_with_real_actions(self):
        path = self._create_excel_file()
        report_dir = tempfile.mkdtemp()
        report_path = os.path.join(report_dir, "normal_report.csv")

        try:
            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
                report_file=report_path,
            )

            with open(report_path, newline="", encoding="utf-8") as report_file:
                first_rows = list(csv.DictReader(report_file))

            self.assertEqual(len(first_rows), 1)
            self.assertEqual(first_rows[0]["action"], "created")
            self.assertTrue(first_rows[0]["event_id"])
            self.assertEqual(first_rows[0]["title"], "Zwolle Test Event")

            call_command(
                "import_events_excel",
                file=path,
                city="zwolle",
                source="excel_zwolle_test",
                report_file=report_path,
            )

            with open(report_path, newline="", encoding="utf-8") as report_file:
                second_rows = list(csv.DictReader(report_file))

            self.assertEqual(len(second_rows), 1)
            self.assertEqual(second_rows[0]["action"], "updated")
            self.assertEqual(second_rows[0]["event_id"], first_rows[0]["event_id"])
        finally:
            if os.path.exists(path):
                os.unlink(path)


class CityContentImportCommandTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Harderwijk", slug="harderwijk")
        self.category, _ = Category.objects.get_or_create(
            slug="cultuur",
            defaults={"name": "Cultuur", "kind": Event.Kind.EVENT},
        )

    def _create_city_content_excel_file(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Master template"
        sheet.append([
            "City",
            "Naam/Activiteit",
            "Slug",
            "Kind",
            "Category",
            "DatumRaw",
            "Venue",
            "Address",
            "Latitude",
            "Longitude",
            "Summary",
            "Omschrijving",
            "SourceUrl",
            "ImageUrl",
            "PriceNote",
            "IndoorOutdoor",
            "WeatherSuitability",
            "LastCheckedAt",
        ])
        sheet.append([
            "harderwijk",
            "Nieuwe stadswandeling",
            "nieuwe-stadswandeling",
            "activity",
            "Cultuur",
            "1 januari 2026",
            "Binnenstad",
            "Markt 1",
            "52.350000",
            "5.620000",
            "Een compacte stadswandeling.",
            "Een volledige beschrijving van de stadswandeling door Harderwijk.",
            "https://example.com/nieuwe-stadswandeling",
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])
        sheet.append([
            "harderwijk",
            "Bestaande stadswandeling",
            "bestaande-stadswandeling",
            "activity",
            "Cultuur",
            "2 januari 2026",
            "Binnenstad",
            "Markt 2",
            "52.350001",
            "5.620001",
            "Een bestaande stadswandeling.",
            "Een volledige beschrijving van een bestaande stadswandeling.",
            "https://example.com/bestaande-stadswandeling-nieuwe-bron",
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])
        sheet.append([
            "harderwijk",
            "",
            "",
            "activity",
            "Cultuur",
            "3 januari 2026",
            "Binnenstad",
            "Markt 3",
            "52.350002",
            "5.620002",
            "Deze rij mist een titel.",
            "Deze rij heeft expres een ontbrekende titel en mag niet importeren.",
            "https://example.com/missing-title",
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def _create_city_content_excel_file_with_shared_source_url(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Master template"
        sheet.append([
            "City",
            "Naam/Activiteit",
            "Slug",
            "Kind",
            "Category",
            "DatumRaw",
            "Venue",
            "Address",
            "Latitude",
            "Longitude",
            "Summary",
            "Omschrijving",
            "SourceUrl",
            "ImageUrl",
            "PriceNote",
            "IndoorOutdoor",
            "WeatherSuitability",
            "LastCheckedAt",
        ])
        shared_source_url = "https://example.com/amersfoort-agenda"
        sheet.append([
            "harderwijk",
            "Eerste agenda-item",
            "eerste-agenda-item",
            "event",
            "Cultuur",
            "1 januari 2026",
            "Binnenstad",
            "Markt 1",
            "52.350000",
            "5.620000",
            "Een compact agenda-item.",
            "Een volledige beschrijving van het eerste agenda-item.",
            shared_source_url,
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])
        sheet.append([
            "harderwijk",
            "Tweede agenda-item",
            "tweede-agenda-item",
            "event",
            "Cultuur",
            "2 januari 2026",
            "Binnenstad",
            "Markt 2",
            "52.350001",
            "5.620001",
            "Nog een compact agenda-item.",
            "Een volledige beschrijving van het tweede agenda-item.",
            shared_source_url,
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def _create_city_content_excel_file_with_blank_ticket_url(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Master template"
        sheet.append([
            "City",
            "Naam/Activiteit",
            "Slug",
            "Kind",
            "Category",
            "DatumRaw",
            "Venue",
            "Address",
            "Latitude",
            "Longitude",
            "Summary",
            "Omschrijving",
            "SourceUrl",
            "TicketUrl",
            "ImageUrl",
            "PriceNote",
            "IndoorOutdoor",
            "WeatherSuitability",
            "LastCheckedAt",
        ])
        sheet.append([
            "harderwijk",
            "Ticketloze stadswandeling",
            "ticketloze-stadswandeling",
            "activity",
            "Cultuur",
            "1 januari 2026",
            "Binnenstad",
            "Markt 1",
            "52.350000",
            "5.620000",
            "Een compacte stadswandeling.",
            "Een volledige beschrijving van de stadswandeling door Harderwijk.",
            "https://example.com/ticketloze-stadswandeling",
            "",
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def _create_city_content_excel_file_with_review_fields(self, row_values):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Master template"
        sheet.append([
            "City",
            "Naam/Activiteit",
            "Slug",
            "Kind",
            "Category",
            "DatumRaw",
            "Venue",
            "Address",
            "Latitude",
            "Longitude",
            "Summary",
            "Omschrijving",
            "SourceUrl",
            "ImageUrl",
            "PriceNote",
            "IndoorOutdoor",
            "WeatherSuitability",
            "LastCheckedAt",
            "RatingValue",
            "ReviewCount",
            "RatingSource",
            "RatingMax",
            "RatingUrl",
            "RatingLastCheckedAt",
            "Rating",
        ])
        defaults = {
            "title": "Review stadswandeling",
            "slug": "review-stadswandeling",
            "rating_value": "",
            "review_count": "",
            "rating_source": "",
            "rating_max": "",
            "rating_url": "",
            "rating_last_checked_at": "",
            "rating": "",
        }
        values = {**defaults, **row_values}
        sheet.append([
            "harderwijk",
            values["title"],
            values["slug"],
            "activity",
            "Cultuur",
            "1 januari 2026",
            "Binnenstad",
            "Markt 1",
            "52.350000",
            "5.620000",
            "Een compacte reviewwandeling.",
            "Een volledige beschrijving van de reviewwandeling door Harderwijk.",
            f"https://example.com/{values['slug']}",
            "",
            "",
            "outdoor",
            "sun",
            "2026-05-13",
            values["rating_value"],
            values["review_count"],
            values["rating_source"],
            values["rating_max"],
            values["rating_url"],
            values["rating_last_checked_at"],
            values["rating"],
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def _create_prepare_city_content_excel_file(self, duplicate_slug=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Master template"
        sheet.append([
            "City",
            "Naam/Activiteit",
            "Slug",
            "Kind",
            "Category",
            "DatumRaw",
            "StartAt",
            "EndAt",
            "Venue",
            "Address",
            "Latitude",
            "Longitude",
            "Summary",
            "Omschrijving",
            "Website",
            "SourceUrl",
            "TicketUrl",
            "VenueWebsite",
            "ImageUrl",
            "PriceNote",
            "LastCheckedAt",
        ])
        first_slug = "winterprogramma-2026-01-01"
        second_slug = first_slug if duplicate_slug else "winterprogramma-2026-01-02"
        sheet.append([
            "harderwijk",
            "  Winterprogramma  ",
            first_slug,
            "event",
            "Cultuur",
            "1 januari 2026",
            "2026-01-01T10:00:00",
            "2026-01-01T12:00:00",
            "Binnenstad",
            "Markt 1",
            "52.350000",
            "5.620000",
            "Een compact winterprogramma.",
            "Een volledige beschrijving van het winterprogramma.",
            " nan ",
            " https://example.com/winterprogramma ",
            "None",
            "null",
            "",
            "",
            "2026-05-13",
        ])
        sheet.append([
            "harderwijk",
            "Winterprogramma",
            second_slug,
            "event",
            "Cultuur",
            "2 januari 2026",
            "2026-01-02T10:00:00",
            "2026-01-02T12:00:00",
            "Binnenstad",
            "Markt 1",
            "52.350001",
            "5.620001",
            "Een compact winterprogramma.",
            "Een volledige beschrijving van het winterprogramma op dag twee.",
            "",
            "https://example.com/winterprogramma",
            "",
            "",
            "",
            "",
            "2026-05-13",
        ])

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_file.close()
        workbook.save(temp_file.name)
        return temp_file.name

    def test_city_content_dry_run_does_not_write_database(self):
        path = self._create_city_content_excel_file()
        before_counts = {
            "events": Event.objects.count(),
            "venues": Venue.objects.count(),
            "tags": Tag.objects.count(),
        }
        stdout = StringIO()

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                dry_run=True,
                no_report_file=True,
                stdout=stdout,
            )
        finally:
            if os.path.exists(path):
                os.unlink(path)

        self.assertEqual(Event.objects.count(), before_counts["events"])
        self.assertEqual(Venue.objects.count(), before_counts["venues"])
        self.assertEqual(Tag.objects.count(), before_counts["tags"])
        self.assertIn("DRY RUN ONLY: no database changes were written.", stdout.getvalue())

    def test_city_content_commit_imports_valid_rows_and_skips_errors_and_duplicates(self):
        existing = Event.objects.create(
            title="Bestaande stadswandeling",
            slug="bestaande-stadswandeling",
            kind=Event.Kind.ACTIVITY,
            city=self.city,
            summary="Niet overschrijven",
            source_url="https://example.com/originele-bron",
        )
        path = self._create_city_content_excel_file()
        report_dir = tempfile.mkdtemp()
        report_path = os.path.join(report_dir, "city_content_commit.json")
        stdout = StringIO()

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                report_file=report_path,
                stdout=stdout,
            )

            self.assertEqual(Event.objects.filter(city=self.city).count(), 2)
            imported = Event.objects.get(slug="nieuwe-stadswandeling")
            self.assertEqual(imported.kind, Event.Kind.ACTIVITY)
            self.assertEqual(imported.source, "city_content:outings")
            self.assertEqual(imported.category, self.category)

            existing.refresh_from_db()
            self.assertEqual(existing.summary, "Niet overschrijven")
            self.assertEqual(existing.source_url, "https://example.com/originele-bron")

            with open(report_path, encoding="utf-8") as report_file:
                report = json.load(report_file)

            self.assertEqual(report["summary"]["mode"], "commit")
            self.assertEqual(report["summary"]["total_rows"], 3)
            self.assertEqual(report["summary"]["valid_rows"], 2)
            self.assertEqual(report["summary"]["rows_with_errors"], 1)
            self.assertEqual(report["summary"]["imported_rows"], 1)
            self.assertEqual(report["summary"]["skipped_error_rows"], 1)
            self.assertEqual(report["summary"]["skipped_duplicate_rows"], 1)
            self.assertEqual(report["summary"]["not_imported_rows"], 2)

            actions = {row["row_number"]: row["action"] for row in report["rows"]}
            self.assertEqual(actions[2], "imported")
            self.assertEqual(actions[3], "skipped_duplicate")
            self.assertEqual(actions[4], "skipped_error")
            self.assertIn("COMMIT complete", stdout.getvalue())
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_allows_different_slugs_with_same_source_url(self):
        path = self._create_city_content_excel_file_with_shared_source_url()
        report_dir = tempfile.mkdtemp()
        report_path = os.path.join(report_dir, "city_content_shared_source_url.json")
        stdout = StringIO()

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                report_file=report_path,
                stdout=stdout,
            )

            self.assertEqual(Event.objects.filter(city=self.city).count(), 2)
            self.assertTrue(Event.objects.filter(slug="eerste-agenda-item").exists())
            self.assertTrue(Event.objects.filter(slug="tweede-agenda-item").exists())

            with open(report_path, encoding="utf-8") as report_file:
                report = json.load(report_file)

            self.assertEqual(report["summary"]["imported_rows"], 2)
            self.assertEqual(report["summary"]["skipped_duplicate_rows"], 0)
            actions = {row["row_number"]: row["action"] for row in report["rows"]}
            self.assertEqual(actions[2], "imported")
            self.assertEqual(actions[3], "imported")
            self.assertTrue(
                all("shared_source_url in file" in row["warnings"] for row in report["rows"])
            )
            self.assertIn("COMMIT complete", stdout.getvalue())
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_does_not_store_blank_ticket_url_as_nan(self):
        path = self._create_city_content_excel_file_with_blank_ticket_url()
        stdout = StringIO()

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                no_report_file=True,
                stdout=stdout,
            )

            imported = Event.objects.get(slug="ticketloze-stadswandeling")
            self.assertIsNone(imported.ticket_url)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_imports_public_review_fields(self):
        path = self._create_city_content_excel_file_with_review_fields(
            {
                "rating_value": "4,6",
                "review_count": "128",
                "rating_source": "Google",
                "rating_max": "5",
                "rating_url": "https://example.com/reviews",
                "rating_last_checked_at": "2026-05-29",
            }
        )

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                no_report_file=True,
                stdout=StringIO(),
            )

            imported = Event.objects.get(slug="review-stadswandeling")
            self.assertEqual(str(imported.rating_value), "4.60")
            self.assertEqual(imported.review_count, 128)
            self.assertEqual(imported.rating_source, "Google")
            self.assertEqual(str(imported.rating_max), "5.00")
            self.assertEqual(imported.rating_url, "https://example.com/reviews")
            self.assertEqual(imported.rating_last_checked_at.isoformat(), "2026-05-29")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_ignores_empty_nan_and_bad_review_values(self):
        path = self._create_city_content_excel_file_with_review_fields(
            {
                "slug": "lege-reviewvelden",
                "title": "Lege reviewvelden",
                "rating_value": "nan",
                "review_count": "None",
                "rating_source": "null",
                "rating_max": "bad",
                "rating_url": "nan",
                "rating_last_checked_at": "not-a-date",
            }
        )

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                no_report_file=True,
                stdout=StringIO(),
            )

            imported = Event.objects.get(slug="lege-reviewvelden")
            self.assertIsNone(imported.rating_value)
            self.assertIsNone(imported.review_count)
            self.assertIsNone(imported.rating_source)
            self.assertIsNone(imported.rating_max)
            self.assertIsNone(imported.rating_url)
            self.assertIsNone(imported.rating_last_checked_at)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_ignores_composite_legacy_rating_text(self):
        path = self._create_city_content_excel_file_with_review_fields(
            {
                "slug": "samengestelde-rating",
                "title": "Samengestelde rating",
                "rating": "8,6/10 (21 stemmen, 0 reviews) - locatie",
            }
        )

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                no_report_file=True,
                stdout=StringIO(),
            )

            imported = Event.objects.get(slug="samengestelde-rating")
            self.assertIsNone(imported.rating_value)
            self.assertIsNone(imported.review_count)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_city_content_commit_imports_numeric_legacy_rating_only(self):
        path = self._create_city_content_excel_file_with_review_fields(
            {
                "slug": "numerieke-rating",
                "title": "Numerieke rating",
                "rating": "4,7",
            }
        )

        try:
            call_command(
                "import_city_content",
                file=path,
                city="harderwijk",
                type="outings",
                commit=True,
                no_report_file=True,
                stdout=StringIO(),
            )

            imported = Event.objects.get(slug="numerieke-rating")
            self.assertEqual(str(imported.rating_value), "4.70")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_prepare_city_import_batch_normalizes_urls_and_auto_fixes_date_series_titles(self):
        path = self._create_prepare_city_content_excel_file()
        output_path = path.replace(".xlsx", "_prepared.xlsx")
        stdout = StringIO()

        try:
            call_command(
                "prepare_city_import_batch",
                file=path,
                city="harderwijk",
                type="outings",
                stdout=stdout,
            )

            self.assertTrue(os.path.exists(output_path))
            original = load_workbook(path)
            prepared = load_workbook(output_path)
            original_sheet = original["Master template"]
            prepared_sheet = prepared["Master template"]

            self.assertEqual(original_sheet["B2"].value, "  Winterprogramma  ")
            self.assertEqual(prepared_sheet["B2"].value, "Winterprogramma - 1 januari 2026")
            self.assertEqual(prepared_sheet["B3"].value, "Winterprogramma - 2 januari 2026")
            self.assertIn(prepared_sheet["O2"].value, (None, ""))
            self.assertIn(prepared_sheet["Q2"].value, (None, ""))
            self.assertIn(prepared_sheet["R2"].value, (None, ""))
            self.assertIn("Auto fixes: 2 titles, 4 URL fields", stdout.getvalue())
            self.assertIn("Ready for dry-run: yes", stdout.getvalue())
        finally:
            for cleanup_path in [path, output_path]:
                if os.path.exists(cleanup_path):
                    os.unlink(cleanup_path)

    def test_prepare_city_import_batch_duplicate_slug_is_blocking(self):
        path = self._create_prepare_city_content_excel_file(duplicate_slug=True)
        output_path = path.replace(".xlsx", "_prepared.xlsx")
        stdout = StringIO()

        try:
            call_command(
                "prepare_city_import_batch",
                file=path,
                city="harderwijk",
                type="outings",
                stdout=stdout,
            )

            self.assertTrue(os.path.exists(output_path))
            self.assertIn("Blocking issues:", stdout.getvalue())
            self.assertIn("duplicate_slug", stdout.getvalue())
            self.assertIn("Ready for dry-run: no", stdout.getvalue())
        finally:
            for cleanup_path in [path, output_path]:
                if os.path.exists(cleanup_path):
                    os.unlink(cleanup_path)

    def test_prepare_city_import_batch_does_not_write_database(self):
        path = self._create_prepare_city_content_excel_file()
        output_path = path.replace(".xlsx", "_prepared.xlsx")
        before_counts = {
            "events": Event.objects.count(),
            "venues": Venue.objects.count(),
            "tags": Tag.objects.count(),
        }

        try:
            call_command(
                "prepare_city_import_batch",
                file=path,
                city="harderwijk",
                type="outings",
                dry_run_after_clean=True,
                stdout=StringIO(),
            )

            self.assertEqual(Event.objects.count(), before_counts["events"])
            self.assertEqual(Venue.objects.count(), before_counts["venues"])
            self.assertEqual(Tag.objects.count(), before_counts["tags"])
        finally:
            for cleanup_path in [path, output_path]:
                if os.path.exists(cleanup_path):
                    os.unlink(cleanup_path)
