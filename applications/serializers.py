import os

from rest_framework import serializers

from .models import Application, Notification, Resume


class ResumeSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = Resume
        fields = ("id", "title", "file_name", "uploaded_at")
        read_only_fields = ("id", "uploaded_at")

    def get_file_name(self, obj):
        return os.path.basename(obj.file.name)


class ResumeUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ("title", "file")

    def validate_file(self, uploaded_file):
        name = uploaded_file.name or ""
        extension = os.path.splitext(name)[1].lower()
        if extension not in {".pdf", ".docx"}:
            raise serializers.ValidationError("Only PDF and DOCX files are accepted.")
        if not uploaded_file.size:
            raise serializers.ValidationError("The file must not be empty.")
        if uploaded_file.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The file must be no larger than 2 MB.")

        uploaded_file.seek(0)
        header = uploaded_file.read(5)
        uploaded_file.seek(0)
        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise serializers.ValidationError("The PDF file content is invalid.")
        if extension == ".docx" and not header.startswith(b"PK"):
            raise serializers.ValidationError("The DOCX file content is invalid.")
        return uploaded_file


class StrictIdField(serializers.Field):
    default_error_messages = {"invalid": "A valid integer id is required."}

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return data

    def to_representation(self, value):
        return value.pk


class ApplySerializer(serializers.Serializer):
    job = StrictIdField()
    resume = StrictIdField()


class ApplicationSerializer(serializers.ModelSerializer):
    job = serializers.IntegerField(source="job_id", read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    company_name = serializers.CharField(source="job.company.name", read_only=True)
    candidate_username = serializers.CharField(source="candidate.username", read_only=True)
    resume = serializers.IntegerField(source="resume_id", read_only=True)

    class Meta:
        model = Application
        fields = (
            "id",
            "job",
            "job_title",
            "company_name",
            "candidate_username",
            "resume",
            "status",
            "applied_at",
            "updated_at",
        )


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Application.STATUS_CHOICES)


class NotificationSerializer(serializers.ModelSerializer):
    application = serializers.IntegerField(source="application_id", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "message", "application", "is_read", "created_at")
