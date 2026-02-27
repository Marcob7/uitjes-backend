# events/feedback_views.py

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .serializers import FeedbackSerializer

@api_view(["POST"])
def feedback_create(request):
    serializer = FeedbackSerializer(data=request.data)

    # Validatie (bijv. message min 10 tekens)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Sla alleen velden op die écht op het Feedback model bestaan
    feedback = serializer.save(
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        # ip_address bewust weggelaten, omdat je model dat veld niet heeft
    )

    return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)
