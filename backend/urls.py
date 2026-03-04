from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse


@ensure_csrf_cookie
def csrf(request):
    # Zet (of refresh) de csrftoken cookie en geef iets simpels terug
    return JsonResponse({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),

    # CSRF cookie endpoint (belangrijk voor POST/PUT/DELETE met cookies)
    path("api/csrf/", csrf),

    # API routes
    path("api/", include("events.urls")),

    # Auth
    path("accounts/", include("allauth.urls")),
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
]