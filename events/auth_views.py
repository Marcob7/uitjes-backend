from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken


class EmailOrUsernameTokenSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        "missing_credentials": "Geef een username of e-mail en wachtwoord mee.",
        "invalid_credentials": "Geen actief account gevonden met deze gegevens.",
    }

    def validate(self, attrs):
        identifier = (attrs.get("username") or attrs.get("email") or "").strip()
        password = attrs.get("password")

        if not identifier or not password:
            raise serializers.ValidationError(
                {"detail": self.error_messages["missing_credentials"]},
                code="authorization",
            )

        username = identifier
        if "@" in identifier:
            user = (
                get_user_model()
                .objects.filter(email__iexact=identifier, is_active=True)
                .order_by("id")
                .first()
            )
            if user is not None:
                username = user.get_username()

        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )

        if user is None or not user.is_active:
            raise serializers.ValidationError(
                {"detail": self.error_messages["invalid_credentials"]},
                code="authorization",
            )

        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


@api_view(["POST"])
@permission_classes([AllowAny])
def token_obtain_pair(request):
    serializer = EmailOrUsernameTokenSerializer(
        data=request.data,
        context={"request": request},
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

    return Response(serializer.validated_data)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def auth_me(request):
    user = request.user
    return Response({
        "id": user.id,
        "username": getattr(user, "username", ""),
        "email": getattr(user, "email", ""),
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "is_authenticated": True,
    })
