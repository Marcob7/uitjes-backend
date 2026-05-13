from datetime import datetime, time, timedelta
import hashlib
import re
import time as pytime

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.http import require_GET

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Category, City, Event, Favorite, Feedback, Tag
from .serializers import (
    CategorySerializer,
    CityContentSerializer,
    CitySerializer,
    EventSerializer,
    FavoriteSerializer,
    FeedbackSerializer,
    TagSerializer,
)


URL_REGEX = re.compile(r"(https?://|www\.)", re.IGNORECASE)


def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hash_ip(ip: str) -> str:
    if not ip:
        return "no-ip"
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def count_links(text: str) -> int:
    if not text:
        return 0
    return len(URL_REGEX.findall(text))


def parse_bool(value):
    if value is None:
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_csv_param(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def has_text(value):
    return bool(str(value or "").strip())


def event_discover_missing_fields(event):
    missing_fields = []

    if not has_text(event.title):
        missing_fields.append("title")
    if not event.city_id:
        missing_fields.append("city")
    if not event.category_id:
        missing_fields.append("category")
    if not has_text(event.summary):
        missing_fields.append("summary")
    if not has_text(event.image_url):
        missing_fields.append("image_url")
    if not event.venue_id and not has_text(event.address):
        missing_fields.append("venue_or_address")
    if not event.start_at and not has_text(event.raw_date_text) and not has_text(event.date_text):
        missing_fields.append("date")

    return missing_fields


def event_is_discover_ready(event):
    return not event_discover_missing_fields(event)


def get_discover_ready_filter():
    has_location = Q(venue__isnull=False) | (
        Q(address__isnull=False) & ~Q(address__exact="")
    )
    has_date = (
        Q(start_at__isnull=False)
        | (Q(raw_date_text__isnull=False) & ~Q(raw_date_text__exact=""))
        | (Q(date_text__isnull=False) & ~Q(date_text__exact=""))
    )

    return (
        Q(title__isnull=False)
        & ~Q(title__exact="")
        & Q(city__isnull=False)
        & Q(category__isnull=False)
        & Q(summary__isnull=False)
        & ~Q(summary__exact="")
        & Q(image_url__isnull=False)
        & ~Q(image_url__exact="")
        & has_location
        & has_date
    )


def get_effective_coordinates_filter():
    event_coordinates = Q(latitude__isnull=False) & Q(longitude__isnull=False)
    venue_coordinates = Q(venue__latitude__isnull=False) & Q(venue__longitude__isnull=False)
    return event_coordinates | venue_coordinates


def get_base_event_queryset():
    return (
        Event.objects.select_related("city", "venue", "category")
        .prefetch_related("tags")
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


def apply_when_filter(qs, when):
    if not when:
        return qs

    now_local = timezone.localtime(timezone.now())

    if when == "tonight":
        start_dt = now_local.replace(hour=18, minute=0, second=0, microsecond=0)
        end_of_day = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        if now_local > start_dt:
            start_dt = now_local

        return qs.filter(start_at__gte=start_dt, start_at__lte=end_of_day)

    if when == "weekend":
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

        return qs.filter(start_at__gte=start_dt, start_at__lt=monday_start)

    return qs


def apply_event_filters(qs, params):
    city = params.get("city")
    free = params.get("free")
    when = params.get("when")
    q = params.get("q")
    search = params.get("search")
    date_exact = params.get("date")
    date_from = params.get("from")
    date_to = params.get("to")
    ongoing = params.get("ongoing")
    category = params.get("category")
    kind = params.get("kind")
    indoor_outdoor = params.get("indoor_outdoor")
    weather = params.get("weather")
    audience = parse_csv_param(params.get("audience"))
    moment = parse_csv_param(params.get("moment"))
    vibe = parse_csv_param(params.get("vibe"))

    needs_distinct = False

    if city:
        qs = qs.filter(city__slug=city)

    if free == "1":
        qs = qs.filter(is_free=True)

    search_value = (search or q or "").strip()
    if search_value:
        qs = qs.filter(
            Q(title__icontains=search_value)
            | Q(summary__icontains=search_value)
            | Q(description__icontains=search_value)
            | Q(venue__name__icontains=search_value)
            | Q(city__name__icontains=search_value)
            | Q(category__name__icontains=search_value)
            | Q(tags__name__icontains=search_value)
        )
        needs_distinct = True

    if date_exact:
        qs = qs.filter(start_at__date=date_exact)
    if date_from:
        qs = qs.filter(start_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(start_at__date__lte=date_to)

    if ongoing in {"0", "1"}:
        now = timezone.now()
        ongoing_window = Q(start_at__lte=now, end_at__gte=now)

        if ongoing == "1":
            qs = qs.filter(ongoing_window)
        else:
            qs = qs.exclude(ongoing_window)

    if category:
        qs = qs.filter(category__slug=category)

    if kind:
        qs = qs.filter(kind=kind)

    if indoor_outdoor:
        qs = qs.filter(indoor_outdoor=indoor_outdoor)

    if weather:
        qs = qs.filter(weather_suitability=weather)

    if parse_bool(params.get("featured")):
        qs = qs.filter(is_featured=True)

    if parse_bool(params.get("hidden_gem")):
        qs = qs.filter(is_hidden_gem=True)

    if parse_bool(params.get("today")):
        today_local = timezone.localdate()
        qs = qs.filter(start_at__date=today_local)

    weekend_explicit = parse_bool(params.get("weekend"))
    if weekend_explicit:
        qs = apply_when_filter(qs, "weekend")
    else:
        qs = apply_when_filter(qs, when)

    if audience:
        qs = qs.filter(tags__facet=Tag.Facet.AUDIENCE, tags__slug__in=audience)
        needs_distinct = True

    if moment:
        qs = qs.filter(tags__facet=Tag.Facet.MOMENT, tags__slug__in=moment)
        needs_distinct = True

    if vibe:
        qs = qs.filter(tags__facet=Tag.Facet.VIBE, tags__slug__in=vibe)
        needs_distinct = True

    if needs_distinct:
        qs = qs.distinct()

    return qs


def paginate_queryset(qs, params):
    try:
        limit = int(params.get("limit", 20))
    except ValueError:
        limit = 20

    try:
        offset = int(params.get("offset", 0))
    except ValueError:
        offset = 0

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    total = qs.count()
    page_qs = qs[offset: offset + limit]
    next_offset = offset + limit
    has_more = next_offset < total

    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
        "results": EventSerializer(page_qs, many=True).data,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
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
    return JsonResponse({"csrfToken": get_token(request)})


@api_view(["GET"])
@permission_classes([AllowAny])
def cities_list(request):
    qs = City.objects.all().order_by("name")

    if parse_bool(request.query_params.get("active")):
        qs = qs.filter(is_active=True)

    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))

    return Response(CitySerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def city_detail(request, slug):
    try:
        city = City.objects.get(slug=slug)
    except City.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(CitySerializer(city).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def categories_list(request):
    qs = Category.objects.all().order_by("name")

    if parse_bool(request.query_params.get("active")):
        qs = qs.filter(is_active=True)

    kind = request.query_params.get("kind")
    if kind:
        qs = qs.filter(kind=kind)

    return Response(CategorySerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def tags_list(request):
    qs = Tag.objects.all().order_by("facet", "name")

    if parse_bool(request.query_params.get("active")):
        qs = qs.filter(is_active=True)

    facet = request.query_params.get("facet")
    if facet:
        qs = qs.filter(facet=facet)

    return Response(TagSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def events_list(request):
    qs = get_base_event_queryset()
    qs = apply_event_filters(qs, request.query_params)
    return Response(paginate_queryset(qs, request.query_params))


FOOD_DRINK_KINDS = {
    Event.Kind.FOOD_DRINK,
    "snackbar",
    "ice_cream",
    "beach_pavilion",
}


def food_drink_content_query():
    return Q(kind__in=FOOD_DRINK_KINDS) | Q(kind=Event.Kind.PLACE, source="city_content:food_drink")


def apply_city_content_filters(qs, params):
    city = (params.get("city") or "").strip()
    content_type = (params.get("type") or params.get("kind") or "").strip()
    query = (params.get("query") or params.get("q") or params.get("search") or "").strip()

    if city:
        qs = qs.filter(Q(city__slug__iexact=city) | Q(city__name__iexact=city))

    if content_type:
        if content_type == "outings":
            qs = qs.exclude(food_drink_content_query())
        elif content_type == Event.Kind.FOOD_DRINK:
            qs = qs.filter(food_drink_content_query())
        else:
            qs = qs.filter(kind=content_type)

    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(description__icontains=query)
            | Q(venue__name__icontains=query)
            | Q(address__icontains=query)
            | Q(category__name__icontains=query)
            | Q(category__slug__icontains=query)
        )

    return qs.distinct()


@api_view(["GET"])
@permission_classes([AllowAny])
def city_content_list(request):
    qs = get_base_event_queryset()
    qs = apply_city_content_filters(qs, request.query_params)
    return Response(paginate_city_content_queryset(qs, request.query_params))


def paginate_city_content_queryset(qs, params):
    try:
        limit = int(params.get("limit", 20))
    except ValueError:
        limit = 20

    try:
        offset = int(params.get("offset", 0))
    except ValueError:
        offset = 0

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    total = qs.count()
    page_qs = qs[offset: offset + limit]
    next_offset = offset + limit
    has_more = next_offset < total

    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
        "results": CityContentSerializer(page_qs, many=True).data,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def festivals_list(request):
    params = request.query_params.copy()
    params["kind"] = Event.Kind.FESTIVAL
    qs = get_base_event_queryset()
    qs = apply_event_filters(qs, params)
    return Response(paginate_queryset(qs, params))


@api_view(["GET"])
@permission_classes([AllowAny])
def events_data_quality(request):
    qs = Event.objects.select_related("city", "venue", "category").prefetch_related("tags")

    city = (request.query_params.get("city") or "").strip()
    if city:
        qs = qs.filter(city__slug=city)

    total = qs.count()
    discover_ready_filter = get_discover_ready_filter()
    coordinates_filter = get_effective_coordinates_filter()

    aggregates = qs.aggregate(
        with_category=Count("id", filter=Q(category__isnull=False), distinct=True),
        with_summary=Count(
            "id",
            filter=Q(summary__isnull=False) & ~Q(summary__exact=""),
            distinct=True,
        ),
        with_image_url=Count(
            "id",
            filter=Q(image_url__isnull=False) & ~Q(image_url__exact=""),
            distinct=True,
        ),
        with_coordinates=Count("id", filter=coordinates_filter, distinct=True),
        with_venue=Count("id", filter=Q(venue__isnull=False), distinct=True),
        with_start_at=Count("id", filter=Q(start_at__isnull=False), distinct=True),
        with_tags=Count("id", filter=Q(tags__isnull=False), distinct=True),
        featured=Count("id", filter=Q(is_featured=True), distinct=True),
        hidden_gem=Count("id", filter=Q(is_hidden_gem=True), distinct=True),
        discover_ready=Count("id", filter=discover_ready_filter, distinct=True),
    )

    by_city = {
        item["city__slug"]: item["count"]
        for item in qs.values("city__slug").annotate(count=Count("id")).order_by("city__slug")
    }

    incomplete_records = []
    for event in qs.exclude(discover_ready_filter).order_by("id")[:50]:
        missing_fields = event_discover_missing_fields(event)
        incomplete_records.append({
            "id": event.id,
            "title": event.title,
            "city": event.city.slug if event.city_id else None,
            "missing_fields": missing_fields,
            "discover_ready": event_is_discover_ready(event),
        })

    return Response({
        "total_events": total,
        "events_per_city": by_city,
        "with_category": aggregates["with_category"],
        "without_category": total - aggregates["with_category"],
        "with_summary": aggregates["with_summary"],
        "without_summary": total - aggregates["with_summary"],
        "with_image_url": aggregates["with_image_url"],
        "without_image_url": total - aggregates["with_image_url"],
        "with_coordinates": aggregates["with_coordinates"],
        "without_coordinates": total - aggregates["with_coordinates"],
        "with_venue": aggregates["with_venue"],
        "without_venue": total - aggregates["with_venue"],
        "with_start_at": aggregates["with_start_at"],
        "without_start_at": total - aggregates["with_start_at"],
        "with_tags": aggregates["with_tags"],
        "without_tags": total - aggregates["with_tags"],
        "featured": aggregates["featured"],
        "hidden_gem": aggregates["hidden_gem"],
        "discover_ready": aggregates["discover_ready"],
        "not_discover_ready": total - aggregates["discover_ready"],
        "incomplete_records": incomplete_records,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def event_detail(request, event_id):
    try:
        event = (
            Event.objects.select_related("city", "venue", "category")
            .prefetch_related("tags")
            .get(id=event_id)
        )
    except Event.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(EventSerializer(event).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_detail_by_slug(request, slug):
    event = (
        Event.objects.select_related("city", "venue", "category")
        .prefetch_related("tags")
        .filter(slug=slug)
        .order_by("id")
        .first()
    )

    if event is None:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(EventSerializer(event).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def feedback_create(request):
    honeypot = (request.data.get("website") or "").strip()
    if honeypot:
        return Response(
            {"detail": "Spam detected."},
            status=status.HTTP_400_BAD_REQUEST,
        )

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
            cache.set(key, current + 1, timeout=window)

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
        .select_related("event", "event__city", "event__venue", "event__category")
        .prefetch_related("event__tags")
        .order_by("-created_at")
    )

    events = [fav.event for fav in fav_qs]
    data = EventSerializer(events, many=True).data
    return Response(data)
