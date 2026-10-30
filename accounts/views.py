from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """Register a new user account."""

    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)


class MeView(generics.RetrieveAPIView):
    """Return the authenticated user's account details."""

    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user
