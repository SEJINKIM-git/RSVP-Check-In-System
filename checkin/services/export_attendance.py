import csv

from django.http import HttpResponse

from checkin.models import GuestParticipant, RegisteredParticipant


ATTENDANCE_EXPORT_HEADERS = [
    "Type",
    "Name",
    "UNID",
    "Major",
    "Checked In",
    "Check-in Time",
]

RSVP_EXPORT_HEADERS = [
    "Submission Order",
    "Name",
    "UNID",
    "Major",
    "Checked In",
    "Check-in Time",
]


def _format_checkin_time(value):
    return value.isoformat(sep=" ", timespec="seconds") if value else ""


def build_attendance_csv_response():
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="final_attendance.csv"'

    writer = csv.writer(response)
    writer.writerow(ATTENDANCE_EXPORT_HEADERS)

    checked_in_registered = RegisteredParticipant.objects.filter(
        checked_in=True
    ).order_by("submission_order", "id")
    guest_participants = GuestParticipant.objects.all().order_by("-checkin_time", "-created_at", "id")

    for participant in checked_in_registered:
        writer.writerow(
            [
                "Registered",
                participant.name,
                participant.unid,
                participant.major,
                "Yes",
                _format_checkin_time(participant.checkin_time),
            ]
        )

    for guest in guest_participants:
        writer.writerow(
            [
                "Guest",
                guest.name,
                guest.unid,
                guest.major,
                "Yes" if guest.checked_in else "No",
                _format_checkin_time(guest.checkin_time),
            ]
        )

    return response


def build_rsvp_csv_response():
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="rsvp_participants.csv"'

    writer = csv.writer(response)
    writer.writerow(RSVP_EXPORT_HEADERS)

    participants = RegisteredParticipant.objects.all().order_by("submission_order", "id")
    for participant in participants:
        writer.writerow(
            [
                participant.submission_order,
                participant.name,
                participant.unid,
                participant.major,
                "Yes" if participant.checked_in else "No",
                _format_checkin_time(participant.checkin_time),
            ]
        )

    return response
