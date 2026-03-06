from datetime import datetime, time, timedelta
import hashlib
import re
import time as pytime

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, When, Value, IntegerField, Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.http import require_GET

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Event, Feedback, Favorite
from .serializers import EventSerializer, FeedbackSerializer, FavoriteSerializer


# =========================
# Feedback anti-spam helpers
# =========================
URL_REGEX = re.compile(r"(https?://|www\.)", re.IGNORECASE)


def get_client_ip(request):
    """
    Simpele IP detectie. Render zet meestal X-Forwarded-For.
    We pakken het eerste IP in de chain.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hash_ip(ip: str) -> str:
    """
    Hash IP zodat je niet letterlijk IP's opslaat/logt.
    """
    if not ip:
        return "no-ip"
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def count_links(text: str) -> int:
    if not text:
        return 0
    return len(URL_REGEX.findall(text))


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    """
    Geeft info terug over de huidige user (session-cookie).
    Altijd 200, zodat de frontend simpel kan checken.
    """
    if not request.user or not request.user.is_authenticated:
        return Response({"is_authenticated": False, "user": None})

    u = request.user
    return Response({
        "is_authenticated": True,
        "user": {
            "id": u.id,
            "email": getattr(u, "email", ""),
            "username": getattr(u, "username", ""),
            "first_name": getattr(u, "first_name", ""),
            "last_name": getattr(u, "last_name", ""),
        }
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


@require_GET
def csrf(request):
    # get_token zorgt er ook voor dat Django de csrftoken cookie zet
    return JsonResponse({"csrfToken": get_token(request)})


@api_view(["GET"])
@permission_classes([AllowAny])
def events_list(request):
    """
    Query params:
    - city=apeldoorn (City.slug)
    - free=1
    - when=tonight|weekend
    - q=zoekterm
    - from=YYYY-MM-DD
    - to=YYYY-MM-DD
    - ongoing=1 (alleen doorlopend) of ongoing=0 (verberg doorlopend)
    - limit=20 (pagination)
    - offset=0 (pagination)
    """

    qs = (
        Event.objects
        .select_related("city", "venue")
        .all()
        .annotate(
            has_date=Case(
                When(start_at__isnull=False, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("-has_date", "start_at", "title")
    )

    # Query params
    city = request.query_params.get("city")
    free = request.query_params.get("free")
    when = request.query_params.get("when")  # "tonight" | "weekend"
    q = request.query_params.get("q")
    date_from = request.query_params.get("from")  # YYYY-MM-DD
    date_to = request.query_params.get("to")      # YYYY-MM-DD
    ongoing = request.query_params.get("ongoing") # "1" of "0"

    # Filters
    if city:
        qs = qs.filter(city__slug=city)

    if free == "1":
        qs = qs.filter(is_free=True)

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(venue__name__icontains=q)
        )

    if date_from:
        qs = qs.filter(start_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(start_at__date__lte=date_to)

    # Doorlopend filter (zet vóór when=tonight/weekend)
    if ongoing == "1":
        qs = qs.filter(start_at__isnull=True)
    elif ongoing == "0":
        qs = qs.filter(start_at__isnull=False)

    # Tijd-filter: vanavond/weekend (werkt alleen voor events met start_at)
    if when:
        now_local = timezone.localtime(timezone.now())

        if when == "tonight":
            start_dt = now_local.replace(hour=18, minute=0, second=0, microsecond=0)
            end_of_day = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

            if now_local > start_dt:
                start_dt = now_local

            qs = qs.filter(start_at__gte=start_dt, start_at__lte=end_of_day)

        elif when == "weekend":
            weekday = now_local.weekday()
            days_until_saturday = (5 - weekday) % 7

            saturday_date = (now_local + timedelta(days=days_until_saturday)).date()
            saturday_start = timezone.make_aware(datetime.combine(saturday_date, time(0, 0, 0)))

            monday_date = saturday_date + timedelta(days=2)
            monday_start = timezone.make_aware(datetime.combine(monday_date, time(0, 0, 0)))

            if weekday in (5, 6) and now_local > saturday_start:
                start_dt = now_local
            else:
                start_dt = saturday_start

            qs = qs.filter(start_at__gte=start_dt, start_at__lt=monday_start)

    # Pagination: limit/offset
    try:
        limit = int(request.query_params.get("limit", 20))
    except ValueError:
        limit = 20

    try:
        offset = int(request.query_params.get("offset", 0))
    except ValueError:
        offset = 0

    # Grenzen (voorkomt extreme requests)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    total = qs.count()
    page_qs = qs[offset: offset + limit]

    results = EventSerializer(page_qs, many=True).data

    next_offset = offset + limit
    has_more = next_offset < total

    return Response({
        "count": total,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
        "results": results,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def event_detail(request, event_id):
    try:
        event = Event.objects.select_related("city", "venue").get(id=event_id)
    except Event.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    data = EventSerializer(event).data
    return Response(data)


@api_view(["POST"])
@permission_classes([AllowAny])
def feedback_create(request):
    """
    Anti-spam maatregelen (anoniem):
    1) Honeypot: veld 'website' moet leeg blijven
    2) Minimum time-to-submit: 'form_started_at' (ms) moet >= FEEDBACK_MIN_SECONDS geleden zijn
    3) Rate limit per IP hash: max FEEDBACK_RATE_LIMIT_MAX per window
    4) Basic content checks: min lengte, max links

    Let op:
    - frontend stuurt extra velden mee zoals 'website' en 'form_started_at'
    - die slaan we NIET op in het model
    - daarom maken we hieronder een schone payload voor de serializer
    """

    # ---- 1) Honeypot ----
    honeypot = (request.data.get("website") or "").strip()
    if honeypot:
        return Response(
            {"detail": "Spam detected."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---- 2) Time-to-submit ----
    min_seconds = getattr(settings, "FEEDBACK_MIN_SECONDS", 3)
    started_at = request.data.get("form_started_at")

    try:
        started_at_ms = int(started_at)
        now_ms = int(pytime.time() * 1000)
        elapsed_seconds = (now_ms - started_at_ms) / 1000.0

        if elapsed_seconds < min_seconds:
            return Response(
                {"detail": "Je hebt het formulier te snel verzonden. Probeer het opnieuw."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except (TypeError, ValueError):
        return Response(
            {"detail": "Ongeldige formulierdata."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---- 3) Rate limit per IP ----
    ip = get_client_ip(request)
    ip_h = hash_ip(ip)

    max_hits = getattr(settings, "FEEDBACK_RATE_LIMIT_MAX", 5)
    window = getattr(settings, "FEEDBACK_RATE_LIMIT_WINDOW_SECONDS", 600)

    key = f"feedback:rl:{ip_h}"
    current = cache.get(key, 0)

    if current >= max_hits:
        return Response(
            {"detail": "Je hebt te vaak feedback verstuurd. Probeer het later opnieuw."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if current == 0:
        cache.set(key, 1, timeout=window)
    else:
        try:
            cache.incr(key)
        except ValueError:
            # fallback voor cache backends die moeilijk doen met incr
            cache.set(key, current + 1, timeout=window)

    # ---- 4) Basic content checks ----
    message = (request.data.get("message") or "").strip()

    if len(message) < 10:
        return Response(
            {"detail": "Je bericht moet minimaal 10 tekens bevatten."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_links = getattr(settings, "FEEDBACK_MAX_LINKS", 2)
    if count_links(message) > max_links:
        return Response(
            {"detail": "Je bericht bevat te veel links."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---- 5) Alleen echte model/serializer velden doorgeven ----
    payload = {
        "message": message,
        "email": (request.data.get("email") or "").strip(),
        "page_url": (request.data.get("page_url") or "").strip(),
    }

    serializer = FeedbackSerializer(data=payload)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    feedback = serializer.save(
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
    )

    return Response(
        FeedbackSerializer(feedback).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def favorites_list(request):
    qs = Favorite.objects.filter(user=request.user).order_by("-created_at")
    data = FavoriteSerializer(qs, many=True).data
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def favorites_add(request):
    event_id = request.data.get("event_id")
    if not event_id:
        return Response({"detail": "event_id is required"}, status=400)

    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return Response({"detail": "Event not found"}, status=404)

    fav, created = Favorite.objects.get_or_create(user=request.user, event=event)
    return Response(
        {"event_id": event.id, "created": created},
        status=201 if created else 200,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def favorites_remove(request, event_id):
    Favorite.objects.filter(user=request.user, event_id=event_id).delete()
    return Response(status=204)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def favorites_events(request):
    fav_qs = (
        Favorite.objects
        .filter(user=request.user)
        .select_related("event", "event__city", "event__venue")
        .order_by("-created_at")
    )

    events = [fav.event for fav in fav_qs]
    data = EventSerializer(events, many=True).data
    return Response(data)