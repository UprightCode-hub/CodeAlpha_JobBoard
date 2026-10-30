from rest_framework import serializers

from .models import Company, Job


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ("id", "owner", "name", "description")
        read_only_fields = ("id", "owner")


class JobSerializer(serializers.ModelSerializer):
    min_years_experience = serializers.IntegerField(min_value=0)
    salary_min = serializers.IntegerField(
        min_value=0,
        required=False,
        allow_null=True,
    )
    salary_max = serializers.IntegerField(
        min_value=0,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Job
        fields = (
            "id",
            "company",
            "title",
            "description",
            "location",
            "job_type",
            "work_model",
            "experience_level",
            "min_years_experience",
            "salary_min",
            "salary_max",
            "is_open",
            "created_at",
        )
        read_only_fields = ("id", "company", "is_open", "created_at")

    def validate(self, attrs):
        current_min = attrs.get(
            "salary_min",
            self.instance.salary_min if self.instance is not None else None,
        )
        current_max = attrs.get(
            "salary_max",
            self.instance.salary_max if self.instance is not None else None,
        )
        if current_min is not None and current_max is not None and current_min > current_max:
            raise serializers.ValidationError(
                {"salary_min": "Minimum salary cannot exceed maximum salary."}
            )
        return attrs


class JobReadSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Job
        fields = (
            "id",
            "title",
            "description",
            "location",
            "job_type",
            "work_model",
            "experience_level",
            "min_years_experience",
            "salary_min",
            "salary_max",
            "is_open",
            "created_at",
            "company_name",
        )
