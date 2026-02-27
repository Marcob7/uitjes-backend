from datetime import datetime, time, timedelta

from django.db.models import Case, When, Value, IntegerField, Q
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Event, Feedback, Favorite
from .serializers import EventSerializer, FeedbackSerializer, FavoriteSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


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
    serializer = FeedbackSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    feedback = serializer.save(
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
    )

    return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


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