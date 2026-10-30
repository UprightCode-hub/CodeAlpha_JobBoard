from django.contrib import admin

from .models import Company, Job


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    search_fields = ("name", "owner__username", "owner__email")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "job_type", "work_model", "is_open", "created_at")
    search_fields = ("title", "description", "location", "company__name")
    list_filter = ("job_type", "work_model", "experience_level", "is_open")
