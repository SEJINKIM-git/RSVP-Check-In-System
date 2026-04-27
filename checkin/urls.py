from django.urls import path

from checkin import views


app_name = "checkin"

urlpatterns = [
    path("import/", views.import_rsvp_view, name="import_rsvp"),
    path("participants/<int:participant_id>/toggle-checkin/", views.toggle_checkin, name="toggle_checkin"),
    path("export/", views.export_attendance_view, name="export_attendance"),
]
