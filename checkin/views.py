from django.db import transaction
from django.db.models import F
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from checkin.forms import GuestCheckInForm
from checkin.models import GuestParticipant, RegisteredParticipant
from checkin.services.export_attendance import (
    build_attendance_csv_response,
    build_rsvp_csv_response,
)
from checkin.services.import_rsvp import import_rsvp_file


def _redirect_to_next(request, fallback_name):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback_name)


def dashboard_view(request):
    total_rsvp = RegisteredParticipant.objects.count()
    registered_checked_in = RegisteredParticipant.objects.filter(checked_in=True).count()
    guest_count = GuestParticipant.objects.count()
    guest_checked_in = GuestParticipant.objects.filter(checked_in=True).count()
    checked_in_total = registered_checked_in + guest_checked_in
    total_attendees = total_rsvp + guest_count
    checkin_progress = round((checked_in_total / total_attendees) * 100) if total_attendees else 0

    context = {
        "total_rsvp": total_rsvp,
        "checked_in_total": checked_in_total,
        "guest_count": guest_count,
        "total_attendees": total_attendees,
        "checkin_progress": checkin_progress,
        "has_participants": total_rsvp > 0,
    }
    return render(request, "checkin/dashboard.html", context)


def registered_checkin_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    participants = RegisteredParticipant.objects.all().order_by("submission_order", "id")
    context = {
        "participants": participants,
        "registered_total": participants.count(),
        "checked_in_total": participants.filter(checked_in=True).count(),
    }
    return render(request, "checkin/registered_checkin.html", context)


def guest_checkin_view(request):
    if request.method == "POST":
        form = GuestCheckInForm(request.POST)
        if form.is_valid():
            GuestParticipant.objects.create(
                name=form.cleaned_data["name"],
                unid=form.cleaned_data["unid"],
                major=form.cleaned_data["major"],
                checked_in=True,
                checkin_time=timezone.now(),
            )
            return redirect("checkin:dashboard")
    elif request.method == "GET":
        form = GuestCheckInForm()
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    context = {
        "form": form,
        "guest_count": GuestParticipant.objects.count(),
    }
    return render(request, "checkin/guest_checkin.html", context)


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
    return _redirect_to_next(request, "checkin:import_rsvp")


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
    return _redirect_to_next(request, "checkin:import_rsvp")


def delete_all_guests(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    GuestParticipant.objects.all().delete()
    return redirect("checkin:guest_checkin")
