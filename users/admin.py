# users/admin.py

from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "is_supervisor",
        "is_developer",
    )

    search_fields = (
        "user__username",
    )

    filter_horizontal = (
        "companies",
        "branches",
    )