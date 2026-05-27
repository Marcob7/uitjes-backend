from dataclasses import dataclass

from django.utils import timezone

from .models import Event


FALLBACK_TEST_FESTIVALS = [
    {
        "title": "Dekmantel Festival",
        "date_label": "12 - 14 juli",
        "location_label": "Amsterdamse Bos",
        "description": (
            "Een lokale testselectie voor elektronische muziek, zorgvuldig "
            "gemarkeerd als fallbackdata zolang frontend festivaldata nog niet "
            "met de backend is verbonden."
        ),
        "href": "/festivals/dekmantel-festival",
    },
    {
        "title": "Lowlands",
        "date_label": "15 - 18 augustus",
        "location_label": "Biddinghuizen",
        "description": (
            "Een testblok voor een breed festivalweekend met muziek, kunst en "
            "nachtprogramma."
        ),
        "href": "/festivals/lowlands",
    },
    {
        "title": "North Sea Jazz",
        "date_label": "11 - 13 juli",
        "location_label": "Rotterdam",
        "description": (
            "Een testblok voor jazz, soul en liveprogramma's in de stad."
        ),
        "href": "/festivals/north-sea-jazz",
    },
]


@dataclass
class FestivalNewsletterItem:
    title: str
    date_label: str
    location_label: str
    description: str
    href: str


@dataclass
class FestivalNewsletterPreview:
    subject: str
    intro: str
    festivals: list[FestivalNewsletterItem]
    closing: str
    body: str
    uses_fallback_data: bool


def is_useful_text(value):
    if not isinstance(value, str):
        return False

    normalized = value.strip().lower()
    return normalized and normalized not in {
        "undefined",
        "null",
        "nan",
        "n/a",
        "none",
    }


def clean_text(value):
    return value.strip() if is_useful_text(value) else ""


def truncate_text(value, max_length=220):
    if len(value) <= max_length:
        return value

    return f"{value[: max_length - 1].rstrip()}."


def format_event_date(event):
    if clean_text(event.date_text):
        return clean_text(event.date_text)
    if clean_text(event.raw_date_text):
        return clean_text(event.raw_date_text)
    if event.start_at:
        local_start = timezone.localtime(event.start_at)
        return local_start.strftime("%d-%m-%Y %H:%M")

    return ""


def format_event_location(event):
    if event.venue_id and clean_text(event.venue.name):
        if event.city_id and clean_text(event.city.name):
            return f"{event.venue.name}, {event.city.name}"
        return clean_text(event.venue.name)
    if clean_text(event.address):
        return clean_text(event.address)
    if event.city_id and clean_text(event.city.name):
        return clean_text(event.city.name)

    return ""


def format_event_description(event):
    description = clean_text(event.summary) or clean_text(event.description)
    if description:
        return truncate_text(description)

    if event.category_id and clean_text(event.category.name):
        return f"Een geselecteerde festivaltip in de categorie {event.category.name}."

    return "Een geselecteerde festivaltip voor je volgende uitje."


def get_backend_festival_items(limit):
    festivals = (
        Event.objects.select_related("city", "venue", "category")
        .filter(kind=Event.Kind.FESTIVAL)
        .order_by("start_at", "title")[:limit]
    )

    return [
        FestivalNewsletterItem(
            title=clean_text(event.title) or "Festival tip",
            date_label=format_event_date(event),
            location_label=format_event_location(event),
            description=format_event_description(event),
            href=clean_text(event.ticket_url)
            or clean_text(event.source_url)
            or (f"/events/{event.id}" if event.id else "/festivals"),
        )
        for event in festivals
    ]


def get_fallback_festival_items(limit):
    return [
        FestivalNewsletterItem(
            title=item["title"],
            date_label=item["date_label"],
            location_label=item["location_label"],
            description=item["description"],
            href=item["href"],
        )
        for item in FALLBACK_TEST_FESTIVALS[:limit]
    ]


def build_festival_newsletter_preview(limit=5):
    safe_limit = max(1, min(int(limit), 5))
    festivals = get_backend_festival_items(safe_limit)
    uses_fallback_data = False

    if not festivals:
        festivals = get_fallback_festival_items(safe_limit)
        uses_fallback_data = True

    subject = "Festival tips voor je volgende uitje"
    intro = (
        "Dit is een lokale testmail met festivalinformatie. Er is nog geen "
        "echte mailprovider gekoppeld."
    )
    if uses_fallback_data:
        intro += " De festivalblokken hieronder komen uit gemarkeerde backend fallback-testdata."

    closing = (
        "Dit is een lokale testmail. Er is nog geen echte mailprovider gekoppeld "
        "en er is niets naar nieuwsbriefinschrijvers verstuurd."
    )

    body_parts = [
        "[LOKALE TESTMAIL - GEEN ECHTE VERZENDING]",
        intro,
    ]

    for index, festival in enumerate(festivals, start=1):
        meta = " - ".join(
            part
            for part in [festival.date_label, festival.location_label]
            if is_useful_text(part)
        )
        block_parts = [
            f"{index}. {festival.title}",
            meta,
            festival.description,
            f"Bekijk festival: {festival.href}",
        ]
        body_parts.append("\n".join(part for part in block_parts if is_useful_text(part)))

    body_parts.append(closing)

    return FestivalNewsletterPreview(
        subject=subject,
        intro=intro,
        festivals=festivals,
        closing=closing,
        body="\n\n".join(part for part in body_parts if is_useful_text(part)),
        uses_fallback_data=uses_fallback_data,
    )
