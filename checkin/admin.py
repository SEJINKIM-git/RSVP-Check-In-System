from django.contrib import admin

from checkin.models import GuestParticipant, RegisteredParticipant


@admin.register(RegisteredParticipant)
class RegisteredParticipantAdmin(admin.ModelAdmin):
    list_display = ("submission_order", "name", "unid", "major", "checked_in", "checkin_time")
    list_filter = ("checked_in", "major")
    search_fields = ("name", "unid", "major")
    ordering = ("submission_order", "id")


@admin.register(GuestParticipant)
class GuestParticipantAdmin(admin.ModelAdmin):
    list_display = ("name", "unid", "major", "checked_in", "checkin_time", "created_at")
    list_filter = ("checked_in", "major")
    search_fields = ("name", "unid", "major")
    ordering = ("-checkin_time", "-created_at", "id")
