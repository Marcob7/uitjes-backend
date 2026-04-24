import os
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from .models import Category, City, Event, Favorite, Tag, Venue


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


class FavoritesCompatibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="secret123",
        )
        self.city = City.objects.create(name="Deventer", slug="deventer")
        self.event = Event.objects.create(
            title="Food Festival Deventer",
            slug="food-festival-deventer",
            city=self.city,
            kind=Event.Kind.FESTIVAL,
        )
        Favorite.objects.create(user=self.user, event=self.event)

    def test_favorites_endpoints_still_work(self):
        self.client.force_authenticate(self.user)

        list_response = self.client.get("/api/favorites/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["event_id"], self.event.id)

        events_response = self.client.get("/api/favorites/events/")
        self.assertEqual(events_response.status_code, 200)
        self.assertEqual(events_response.json()[0]["id"], self.event.id)


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
