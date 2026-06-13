from django.urls import path

from checkin import views


app_name = "checkin"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("registered/", views.registered_checkin_view, name="registered_checkin"),
    path("guest/", views.guest_checkin_view, name="guest_checkin"),
    path("import/", views.import_rsvp_view, name="import_rsvp"),
    path("participants/<int:participant_id>/toggle-checkin/", views.toggle_checkin, name="toggle_checkin"),
    path("participants/<int:participant_id>/delete/", views.delete_participant, name="delete_participant"),
    path("participants/delete-all/", views.delete_all_participants, name="delete_all_participants"),
    path("guests/delete-all/", views.delete_all_guests, name="delete_all_guests"),
    path("guests/check-unid/", views.check_unid, name="check_unid"),
    path("export-rsvp/", views.export_rsvp_view, name="export_rsvp"),
    path("export/", views.export_attendance_view, name="export_attendance"),
    path("analytics/", views.analytics_view, name="analytics"),
]
