from django.contrib import admin

from .models import Application, Notification, Resume


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("title", "candidate", "uploaded_at")
    search_fields = ("title", "candidate__username", "candidate__email")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "status", "applied_at", "updated_at")
    search_fields = ("candidate__username", "job__title", "resume__title")
    list_filter = ("status",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "application", "is_read", "created_at")
    search_fields = ("recipient__username", "message", "application__job__title")
    list_filter = ("is_read",)
