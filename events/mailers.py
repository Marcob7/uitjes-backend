from html import escape
from importlib import import_module

from django.conf import settings

from .festival_newsletter import is_useful_text


class NewsletterEmailConfigError(Exception):
    pass


class NewsletterEmailProviderError(Exception):
    pass


def _clean_email_body(body):
    if not isinstance(body, str):
        return ""

    return "\n\n".join(
        part.strip()
        for part in body.split("\n\n")
        if is_useful_text(part)
    )


def _text_to_html(body):
    paragraphs = [
        f"<p>{escape(part).replace(chr(10), '<br>')}</p>"
        for part in body.split("\n\n")
        if is_useful_text(part)
    ]
    return "\n".join(paragraphs)


def _prepare_resend_test_body(body):
    clean_body = _clean_email_body(body)
    replacements = {
        "[LOKALE TESTMAIL - GEEN ECHTE VERZENDING]": "[TESTMAIL - VERZONDEN VIA RESEND]",
        (
            "Dit is een lokale testmail met festivalinformatie. Er is nog geen "
            "echte mailprovider gekoppeld."
        ): (
            "Dit is een echte testmail, verzonden via Resend naar één expliciet "
            "testadres."
        ),
        (
            "Dit is een lokale testmail met evenementen uit de backend jaarkalenderdata. "
            "Er is nog geen echte mailprovider gekoppeld."
        ): (
            "Dit is een echte testmail, verzonden via Resend naar één expliciet "
            "testadres."
        ),
        (
            "Dit is een lokale testmail. Er is nog geen echte mailprovider gekoppeld "
            "en er is niets naar nieuwsbriefinschrijvers verstuurd."
        ): (
            "Er is nog geen bulkverzending naar nieuwsbriefinschrijvers actief."
        ),
    }

    for old, new in replacements.items():
        clean_body = clean_body.replace(old, new)

    return _clean_email_body(clean_body)


def send_resend_newsletter_test(*, to_email, subject, body):
    api_key = getattr(settings, "RESEND_API_KEY", "").strip()
    if not api_key:
        raise NewsletterEmailConfigError(
            "RESEND_API_KEY ontbreekt. Zet deze env-var voordat je een echte "
            "Resend-testmail verstuurt."
        )

    from_email = (
        getattr(settings, "RESEND_FROM_EMAIL", "").strip()
        or getattr(settings, "DEFAULT_FROM_EMAIL", "").strip()
    )
    if not from_email:
        raise NewsletterEmailConfigError(
            "RESEND_FROM_EMAIL of DEFAULT_FROM_EMAIL ontbreekt. Configureer een "
            "geldige, bij Resend verifieerbare afzender."
        )

    clean_subject = subject.strip() if isinstance(subject, str) else ""
    clean_body = _prepare_resend_test_body(body)
    if not clean_subject or not clean_body:
        raise NewsletterEmailConfigError(
            "De testmail heeft geen bruikbaar subject of body en is niet verstuurd."
        )

    try:
        resend = import_module("resend")
    except ImportError as exc:
        raise NewsletterEmailConfigError(
            "De Resend Python dependency ontbreekt. Installeer requirements.txt opnieuw."
        ) from exc

    resend.api_key = api_key
    params = {
        "from": from_email,
        "to": [to_email],
        "subject": clean_subject,
        "text": clean_body,
        "html": _text_to_html(clean_body),
    }

    try:
        response = resend.Emails.send(params)
    except Exception as exc:
        raise NewsletterEmailProviderError(
            f"Resend kon de testmail niet versturen: {exc}"
        ) from exc

    return {
        "provider": "resend",
        "from_email": from_email,
        "to_email": to_email,
        "subject": clean_subject,
        "body": clean_body,
        "response": response,
    }
