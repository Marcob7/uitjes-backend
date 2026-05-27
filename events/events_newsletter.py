from dataclasses import dataclass

from .festival_newsletter import (
    clean_text,
    format_event_date,
    format_event_location,
    is_useful_text,
    truncate_text,
)
from .models import Event


FALLBACK_TEST_EVENTS = [
    {
        "title": "Avondwandeling door de binnenstad",
        "date_label": "Vrijdagavond",
        "location_label": "Binnenstad",
        "description": (
            "Een gemarkeerde fallback-tip voor een ontspannen stadswandeling "
            "wanneer er lokaal nog geen backend-eventdata beschikbaar is."
        ),
        "href": "/jaarkalender",
    },
    {
        "title": "Kleine zaal: live muziek",
        "date_label": "Zaterdag 20:00",
        "location_label": "Podium in de stad",
        "description": "Een gemarkeerde fallback-tip voor een lokaal muziekuitje.",
        "href": "/jaarkalender",
    },
    {
        "title": "Zondagse markt en makers",
        "date_label": "Zondagmiddag",
        "location_label": "Marktplein",
        "description": (
            "Een gemarkeerde fallback-tip voor een laagdrempelig uitje met "
            "lokale makers en activiteiten."
        ),
        "href": "/jaarkalender",
    },
]


@dataclass
class EventsNewsletterItem:
    title: str
    date_label: str
    location_label: str
    description: str
    href: str


@dataclass
class EventsNewsletterPreview:
    subject: str
    intro: str
    events: list[EventsNewsletterItem]
    closing: str
    body: str
    uses_fallback_data: bool


def format_events_description(event):
    description = clean_text(event.summary) or clean_text(event.description)
    if description:
        return truncate_text(description)

    if event.category_id and clean_text(event.category.name):
        return f"Een geselecteerde evenemententip in de categorie {event.category.name}."

    return "Een geselecteerde evenemententip voor je volgende uitje."


def get_backend_event_items(limit):
    events = (
        Event.objects.select_related("city", "venue", "category")
        .filter(kind=Event.Kind.EVENT)
        .order_by("start_at", "title")[:limit]
    )

    return [
        EventsNewsletterItem(
            title=clean_text(event.title) or "Evenemententip",
            date_label=format_event_date(event),
            location_label=format_event_location(event),
            description=format_events_description(event),
            href=clean_text(event.ticket_url)
            or clean_text(event.source_url)
            or (f"/events/{event.id}" if event.id else "/jaarkalender"),
        )
        for event in events
    ]


def get_fallback_event_items(limit):
    return [
        EventsNewsletterItem(
            title=item["title"],
            date_label=item["date_label"],
            location_label=item["location_label"],
            description=item["description"],
            href=item["href"],
        )
        for item in FALLBACK_TEST_EVENTS[:limit]
    ]


def build_events_newsletter_preview(limit=5):
    safe_limit = max(1, min(int(limit), 5))
    events = get_backend_event_items(safe_limit)
    uses_fallback_data = False

    if not events:
        events = get_fallback_event_items(safe_limit)
        uses_fallback_data = True

    subject = "Evenemententips voor je volgende uitje"
    intro = (
        "Dit is een lokale testmail met evenementen uit de backend jaarkalenderdata. "
        "Er is nog geen echte mailprovider gekoppeld."
    )
    if uses_fallback_data:
        intro += " De eventblokken hieronder komen uit gemarkeerde backend fallback-testdata."

    closing = (
        "Dit is een lokale testmail. Er is nog geen echte mailprovider gekoppeld "
        "en er is niets naar nieuwsbriefinschrijvers verstuurd."
    )

    body_parts = [
        "[LOKALE TESTMAIL - GEEN ECHTE VERZENDING]",
        intro,
    ]

    for index, event in enumerate(events, start=1):
        meta = " - ".join(
            part
            for part in [event.date_label, event.location_label]
            if is_useful_text(part)
        )
        block_parts = [
            f"{index}. {event.title}",
            meta,
            event.description,
            f"Bekijk evenement: {event.href}",
        ]
        body_parts.append("\n".join(part for part in block_parts if is_useful_text(part)))

    body_parts.append(closing)

    return EventsNewsletterPreview(
        subject=subject,
        intro=intro,
        events=events,
        closing=closing,
        body="\n\n".join(part for part in body_parts if is_useful_text(part)),
        uses_fallback_data=uses_fallback_data,
    )
