from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import ensure_csrf_cookie

from django.http import JsonResponse

from django.middleware.csrf import get_token

@ensure_csrf_cookie
def csrf(request):
    # ensure_csrf_cookie zet/refresht de cookie
    # get_token geeft de token terug (en zorgt ook dat hij bestaat)
    return JsonResponse({"csrfToken": get_token(request)})


urlpatterns = [
    path("admin/", admin.site.urls),


    # API routes
    path("api/", include("events.urls")),

    # Auth
    path("accounts/", include("allauth.urls")),
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
]