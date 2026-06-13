import json
import os
from collections import Counter, defaultdict

from django.db import transaction
from django.db.models import Count, F
from django.db.models.functions import TruncHour
from django.db.utils import OperationalError, ProgrammingError
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
from checkin.services.import_rsvp import (
    FIELD_LABELS,
    IMPORT_FIELD_NAMES,
    IMPORT_SESSION_KEY,
    REQUIRED_FIELD_NAMES,
    build_import_preview,
    import_rsvp_rows,
    prepare_rsvp_import,
)


DATABASE_UNAVAILABLE_MESSAGE = (
    "The database is not ready for this deployment yet. "
    "On Vercel, set DATABASE_URL to a managed Postgres database and run migrations. "
    "SQLite files from local development are not a reliable production database on Vercel."
)


def _mapping_fields_context(mapping):
    return [
        {
            "name": field,
            "label": FIELD_LABELS[field],
            "selected_header": mapping.get(field, ""),
            "required": field in REQUIRED_FIELD_NAMES,
        }
        for field in IMPORT_FIELD_NAMES
    ]


def _database_unavailable_context():
    return {
        "active_nav": "dashboard",
        "total_rsvp": 0,
        "registered_checked_in": 0,
        "guest_count": 0,
        "current_total_attendance": 0,
        "checkin_progress": 0,
        "has_participants": False,
        "database_warning": DATABASE_UNAVAILABLE_MESSAGE,
        "is_vercel": bool(os.environ.get("VERCEL")),
    }


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
    try:
        total_rsvp = RegisteredParticipant.objects.count()
        registered_checked_in = RegisteredParticipant.objects.filter(checked_in=True).count()
        guest_count = GuestParticipant.objects.count()
        current_total_attendance = registered_checked_in + guest_count
        attendance_pool_total = total_rsvp + guest_count
        checkin_progress = (
            round((current_total_attendance / attendance_pool_total) * 100)
            if attendance_pool_total
            else 0
        )

        context = {
            "active_nav": "dashboard",
            "total_rsvp": total_rsvp,
            "registered_checked_in": registered_checked_in,
            "guest_count": guest_count,
            "current_total_attendance": current_total_attendance,
            "checkin_progress": checkin_progress,
            "has_participants": total_rsvp > 0,
            "database_warning": "",
            "is_vercel": bool(os.environ.get("VERCEL")),
        }
    except (OperationalError, ProgrammingError):
        context = _database_unavailable_context()

    return render(request, "checkin/dashboard.html", context)


def registered_checkin_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    participants = RegisteredParticipant.objects.all().order_by("submission_order", "id")
    context = {
        "active_nav": "registered",
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
        "active_nav": "guest",
        "form": form,
        "guest_count": GuestParticipant.objects.count(),
    }
    return render(request, "checkin/guest_checkin.html", context)


def import_rsvp_view(request):
    context = {
        "active_nav": "data_tools",
        "summary": None,
        "mapping_context": None,
    }

    if request.method == "POST":
        action = request.POST.get("import_action", "preview")

        if action == "confirm":
            pending_import = request.session.get(IMPORT_SESSION_KEY)
            if not pending_import:
                context["summary"] = {
                    "imported_count": 0,
                    "skipped_count": 0,
                    "duplicate_unids": [],
                    "errors": ["No RSVP import preview is waiting for confirmation."],
                }
            else:
                posted_mapping = {
                    field: request.POST.get(f"mapping_{field}", pending_import["mapping"].get(field, ""))
                    for field in IMPORT_FIELD_NAMES
                }
                pending_import["mapping"] = posted_mapping
                context["summary"] = import_rsvp_rows(
                    pending_import["rows"],
                    pending_import["mapping"],
                )
                request.session.pop(IMPORT_SESSION_KEY, None)
        elif action == "cancel":
            request.session.pop(IMPORT_SESSION_KEY, None)
            context["summary"] = None
        elif action == "remap":
            pending_import = request.session.get(IMPORT_SESSION_KEY)
            if not pending_import:
                context["summary"] = {
                    "imported_count": 0,
                    "skipped_count": 0,
                    "duplicate_unids": [],
                    "errors": ["Upload a file before changing column mapping."],
                }
            else:
                mapping = {
                    field: request.POST.get(f"mapping_{field}", "")
                    for field in IMPORT_FIELD_NAMES
                }
                preview = build_import_preview(pending_import["rows"], mapping)
                pending_import["mapping"] = mapping
                request.session[IMPORT_SESSION_KEY] = pending_import
                request.session.modified = True
                context["mapping_context"] = {
                    "headers": pending_import["headers"],
                    "mapping": mapping,
                    "detection": pending_import["detection"],
                    "preview": preview,
                    "mapping_fields": _mapping_fields_context(mapping),
                }
        else:
            uploaded_file = request.FILES.get("rsvp_file")
            prepared_import = prepare_rsvp_import(uploaded_file)
            if prepared_import["errors"]:
                context["summary"] = {
                    "imported_count": 0,
                    "skipped_count": 0,
                    "duplicate_unids": [],
                    "errors": prepared_import["errors"],
                }
            else:
                request.session[IMPORT_SESSION_KEY] = {
                    "headers": prepared_import["headers"],
                    "rows": prepared_import["rows"],
                    "mapping": prepared_import["mapping"],
                    "detection": prepared_import["detection"],
                }
                context["mapping_context"] = {
                    "headers": prepared_import["headers"],
                    "mapping": prepared_import["mapping"],
                    "detection": prepared_import["detection"],
                    "preview": prepared_import["preview"],
                    "mapping_fields": _mapping_fields_context(prepared_import["mapping"]),
                }
    elif request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    participants = RegisteredParticipant.objects.all().order_by("submission_order", "id")
    guest_participants = GuestParticipant.objects.all().order_by("-checkin_time", "-created_at", "id")
    context["participants"] = participants
    context["guest_participants"] = guest_participants
    context["registered_total"] = participants.count()
    context["registered_checked_in"] = participants.filter(checked_in=True).count()
    context["guest_count"] = guest_participants.count()
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

    return _redirect_to_next(request, "checkin:import_rsvp")


def delete_all_participants(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    RegisteredParticipant.objects.all().delete()
    return _redirect_to_next(request, "checkin:import_rsvp")


def delete_all_guests(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    GuestParticipant.objects.all().delete()
    return _redirect_to_next(request, "checkin:guest_checkin")


def _normalize_major(major_str):
    if not major_str or major_str.strip().lower() in ("none", "n/a", "-", "", "null", "na"):
        return "Other"
    return major_str.strip()


def _hour_label(dt):
    h = dt.hour
    period = "AM" if h < 12 else "PM"
    display = h % 12 or 12
    return f"{display}:00 {period}"


def analytics_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    try:
        # Time-based check-in chart (registered + guest)
        hour_counts = defaultdict(int)
        for row in (
            RegisteredParticipant.objects.filter(checked_in=True, checkin_time__isnull=False)
            .annotate(hour=TruncHour("checkin_time"))
            .values("hour")
            .annotate(count=Count("id"))
        ):
            hour_counts[row["hour"]] += row["count"]
        for row in (
            GuestParticipant.objects.filter(checked_in=True, checkin_time__isnull=False)
            .annotate(hour=TruncHour("checkin_time"))
            .values("hour")
            .annotate(count=Count("id"))
        ):
            hour_counts[row["hour"]] += row["count"]

        sorted_hours = sorted(hour_counts)
        checkin_time_labels = [_hour_label(h) for h in sorted_hours]
        checkin_time_values = [hour_counts[h] for h in sorted_hours]

        cumulative, running = [], 0
        for v in checkin_time_values:
            running += v
            cumulative.append(running)

        # Major distribution (all registered + guests with a major)
        major_counter = Counter()
        for p in RegisteredParticipant.objects.values("major"):
            major_counter[_normalize_major(p["major"])] += 1
        for p in GuestParticipant.objects.values("major"):
            if p["major"]:
                major_counter[_normalize_major(p["major"])] += 1

        sorted_majors = sorted(major_counter.items(), key=lambda x: (x[0] == "Other", -x[1]))
        major_labels = [m[0] for m in sorted_majors]
        major_values = [m[1] for m in sorted_majors]

        total_registered = RegisteredParticipant.objects.count()
        total_checked_in = (
            RegisteredParticipant.objects.filter(checked_in=True).count()
            + GuestParticipant.objects.filter(checked_in=True).count()
        )
        total_guest = GuestParticipant.objects.count()

        context = {
            "active_nav": "analytics",
            "checkin_time_labels": json.dumps(checkin_time_labels),
            "checkin_time_values": json.dumps(checkin_time_values),
            "cumulative_values": json.dumps(cumulative),
            "major_labels": json.dumps(major_labels),
            "major_values": json.dumps(major_values),
            "total_registered": total_registered,
            "total_checked_in": total_checked_in,
            "total_guest": total_guest,
            "has_checkin_data": bool(sorted_hours),
            "has_major_data": bool(major_labels),
        }
    except (OperationalError, ProgrammingError):
        context = {
            "active_nav": "analytics",
            "checkin_time_labels": json.dumps([]),
            "checkin_time_values": json.dumps([]),
            "cumulative_values": json.dumps([]),
            "major_labels": json.dumps([]),
            "major_values": json.dumps([]),
            "total_registered": 0,
            "total_checked_in": 0,
            "total_guest": 0,
            "has_checkin_data": False,
            "has_major_data": False,
        }

    return render(request, "checkin/analytics.html", context)
