from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serialize public fields for the authenticated user."""

    class Meta:
        model = User
        fields = ("id", "username", "email", "role")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Validate and create a user account."""

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "role")
        read_only_fields = ("id", "role")

    def create(self, validated_data):
        return User.objects.create_user(role=User.ROLE_CANDIDATE, **validated_data)
