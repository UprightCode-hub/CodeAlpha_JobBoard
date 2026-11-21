import os
import zipfile
from io import BytesIO
from xml.etree import ElementTree

from pypdf import PdfReader
from rest_framework import serializers

from .models import Application, Notification, Resume


class ResumeSerializer(serializers.ModelSerializer):
    """Serialize resume metadata without exposing its file URL."""

    file_name = serializers.SerializerMethodField()

    class Meta:
        model = Resume
        fields = ("id", "title", "file_name", "uploaded_at")
        read_only_fields = ("id", "uploaded_at")

    def get_file_name(self, obj):
        return os.path.basename(obj.file.name)


class ResumeUploadSerializer(serializers.ModelSerializer):
    """Validate resume metadata and uploaded file content."""

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
        content = uploaded_file.read()
        uploaded_file.seek(0)
        if extension == ".pdf":
            self._validate_pdf(content)
        else:
            self._validate_docx(content)
        return uploaded_file

    @staticmethod
    def _validate_pdf(content):
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if not reader.pages:
                raise ValueError("PDF has no pages")
        except Exception as exc:
            raise serializers.ValidationError(
                "The PDF file content is invalid."
            ) from exc

    @staticmethod
    def _validate_docx(content):
        required_parts = {
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
        }
        try:
            with zipfile.ZipFile(BytesIO(content)) as package:
                parts = set(package.namelist())
                if not required_parts.issubset(parts):
                    raise ValueError("DOCX package is missing required parts")
                if (
                    sum(item.file_size for item in package.infolist())
                    > 20 * 1024 * 1024
                ):
                    raise ValueError("DOCX package expands beyond the allowed size")
                if package.testzip() is not None:
                    raise ValueError("DOCX package has a corrupt member")

                content_types = ElementTree.fromstring(
                    package.read("[Content_Types].xml")
                )
                document = ElementTree.fromstring(package.read("word/document.xml"))
                relationships = ElementTree.fromstring(package.read("_rels/.rels"))
                if content_types.tag.rsplit("}", 1)[-1] != "Types":
                    raise ValueError("Invalid OOXML content types")
                main_document_type = (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document.main+xml"
                )
                if not any(
                    item.attrib.get("PartName") == "/word/document.xml"
                    and item.attrib.get("ContentType") == main_document_type
                    for item in content_types
                ):
                    raise ValueError("OOXML package does not declare a Word document")
                if document.tag.rsplit("}", 1)[-1] != "document" or not any(
                    child.tag.rsplit("}", 1)[-1] == "body" for child in document
                ):
                    raise ValueError("Invalid Word document XML")
                if relationships.tag.rsplit("}", 1)[-1] != "Relationships":
                    raise ValueError("Invalid OOXML package relationships")
        except (
            OSError,
            ValueError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            ElementTree.ParseError,
            RuntimeError,
        ) as exc:
            raise serializers.ValidationError(
                "The DOCX file content is invalid."
            ) from exc


class StrictIdField(serializers.Field):
    """Accept integer identifiers without coercing other input types."""

    default_error_messages = {"invalid": "A valid integer id is required."}

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return data

    def to_representation(self, value):
        return value.pk


class ApplySerializer(serializers.Serializer):
    """Validate job and resume identifiers for an application."""

    job = StrictIdField()
    resume = StrictIdField()


class ApplicationSerializer(serializers.ModelSerializer):
    """Serialize application details for candidates and employers."""

    job = serializers.IntegerField(source="job_id", read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    company_name = serializers.CharField(source="job.company.name", read_only=True)
    candidate_username = serializers.CharField(
        source="candidate.username", read_only=True
    )
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
    """Validate an application status value."""

    status = serializers.ChoiceField(choices=Application.STATUS_CHOICES)


class NotificationSerializer(serializers.ModelSerializer):
    """Serialize employer notification details."""

    application = serializers.IntegerField(source="application_id", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "message", "application", "is_read", "created_at")
