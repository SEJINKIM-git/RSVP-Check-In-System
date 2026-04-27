from django.db import transaction
from django.db.models import F
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from checkin.models import RegisteredParticipant
from checkin.services.export_attendance import (
    build_attendance_csv_response,
    build_rsvp_csv_response,
)
from checkin.services.import_rsvp import import_rsvp_file


def import_rsvp_view(request):
    context = {"summary": None}

    if request.method == "POST":
        uploaded_file = request.FILES.get("rsvp_file")
        context["summary"] = import_rsvp_file(uploaded_file)
    elif request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    context["participants"] = RegisteredParticipant.objects.all().order_by("submission_order")
    return render(request, "import_rsvp.html", context)


def export_attendance_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    return build_attendance_csv_response()


def export_rsvp_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    return build_rsvp_csv_response()


def toggle_checkin(request, participant_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    participant = get_object_or_404(RegisteredParticipant, pk=participant_id)
    participant.checked_in = not participant.checked_in
    participant.checkin_time = timezone.now() if participant.checked_in else None
    participant.save(update_fields=["checked_in", "checkin_time", "updated_at"])
    return redirect("checkin:import_rsvp")


def delete_participant(request, participant_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    participant = get_object_or_404(RegisteredParticipant, pk=participant_id)

    with transaction.atomic():
        deleted_order = participant.submission_order
        participant.delete()
        RegisteredParticipant.objects.filter(submission_order__gt=deleted_order).update(
            submission_order=F("submission_order") - 1
        )

    return redirect("checkin:import_rsvp")


def delete_all_participants(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    RegisteredParticipant.objects.all().delete()
    return redirect("checkin:import_rsvp")
