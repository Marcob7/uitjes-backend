from django.urls import path
from .views import (
  categories_list,
  cities_list,
  city_detail,
  event_detail_by_slug,
  events_list,
  event_detail,
  festivals_list,
  favorites_list,
  favorites_add,
  favorites_remove,
  favorites_events,
  csrf,
  feedback_create,
  health,
  me,
  tags_list,
)


urlpatterns = [
  path("health/", health),

  # Public metadata
  path("cities/", cities_list),
  path("cities/<slug:slug>/", city_detail),
  path("categories/", categories_list),
  path("tags/", tags_list),

  # Public events
  path("events/", events_list),
  path("events/by-slug/<slug:slug>/", event_detail_by_slug),
  path("events/<int:event_id>/", event_detail),
  path("festivals/", festivals_list),

  # Feedback (mag public)
  path("feedback/", feedback_create),

  # Favorites (alleen ingelogd)
  path("favorites/", favorites_list),
  path("favorites/add/", favorites_add),
  path("favorites/<int:event_id>/", favorites_remove),

  # Favorites -> volledige events (alleen ingelogd)
  path("favorites/events/", favorites_events),
  
  path("csrf/", csrf),
  path("me/", me),
]
