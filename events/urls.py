from django.urls import path
from .views import (
  events_list,
  event_detail,
  favorites_list,
  favorites_add,
  favorites_remove,
  favorites_events,
)
from .feedback_views import feedback_create

urlpatterns = [
  # Public events
  path("events/", events_list),
  path("events/<int:event_id>/", event_detail),

  # Feedback (mag public)
  path("feedback/", feedback_create),

  # Favorites (alleen ingelogd)
  path("favorites/", favorites_list),
  path("favorites/add/", favorites_add),
  path("favorites/<int:event_id>/", favorites_remove),

  # Favorites -> volledige events (alleen ingelogd)
  path("favorites/events/", favorites_events),
]