import json
import os
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, F, Q
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie

from checkin.forms import GuestCheckInForm
from checkin.models import GuestParticipant, RegisteredParticipant
from checkin.services.export_attendance import (
    build_attendance_csv_response,
    build_current_attendance_group_rows,
    build_rsvp_csv_response,
    build_rsvp_xlsx_response,
)
from checkin.services.import_rsvp import (
    FIELD_LABELS,
    GENERATE_INTERNAL_ID,
    IMPORT_RESULT_SESSION_KEY,
    IMPORT_SESSION_KEY,
    NAME_TIMESTAMP_ID,
    build_import_review,
    build_participant_answers,
    get_import_configuration_snapshot,
    import_rsvp_rows,
    prepare_rsvp_import,
)


DATABASE_UNAVAILABLE_MESSAGE = (
    "The database is not ready for this deployment yet. "
    "On Vercel, set DATABASE_URL to a managed Postgres database and run migrations. "
    "SQLite files from local development are not a reliable production database on Vercel."
)

REGISTERED_PARTICIPANT_LIST_FIELDS = (
    "id",
    "submission_order",
    "name",
    "unid",
    "major",
    "email",
    "answers",
    "checked_in",
    "checkin_time",
)
GUEST_PARTICIPANT_LIST_FIELDS = (
    "id",
    "name",
    "unid",
    "major",
    "checked_in",
    "checkin_time",
    "created_at",
)


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


def _build_search_placeholder(searchable_columns):
    if not searchable_columns:
        return "Search imported RSVP data"
    if len(searchable_columns) <= 3:
        return "Search by " + ", ".join(searchable_columns)
    return "Search selected RSVP columns"


def _count_checked_in(participants):
    return sum(1 for participant in participants if participant.checked_in)


def _build_participant_table_context(participants, configuration):
    display_columns = configuration.get("display_columns") or configuration.get("imported_columns") or []
    searchable_columns = display_columns[:]
    identifier_label = configuration.get("identifier_label") or "Unique Identifier"

    rows = []
    for participant in participants:
        answers = build_participant_answers(participant, configuration)
        display_name = participant.name or participant.unid or "Imported Participant"
        search_text = " ".join(
            str(answers.get(column, "")).lower()
            for column in searchable_columns
        ).strip()
        rows.append(
            {
                "participant": participant,
                "display_name": display_name,
                "avatar_letter": display_name[:1].upper() if display_name else "?",
                "cells": [
                    {
                        "header": column,
                        "value": answers.get(column, "") or "-",
                    }
                    for column in display_columns
                ],
                "search_text": search_text,
            }
        )

    return {
        "columns": display_columns,
        "rows": rows,
        "searchable_columns": searchable_columns,
        "search_placeholder": _build_search_placeholder(searchable_columns),
        "identifier_label": identifier_label,
    }


def _pop_import_summary(request):
    summary = request.session.pop(IMPORT_RESULT_SESSION_KEY, None)
    if summary:
        request.session.modified = True
    return summary


def _pending_import_payload(request):
    return request.session.get(IMPORT_SESSION_KEY)


def _save_pending_import(request, prepared_import):
    request.session[IMPORT_SESSION_KEY] = {
        "headers": prepared_import["headers"],
        "rows": prepared_import["rows"],
        "header_row_number": prepared_import["header_row_number"],
        "detection": prepared_import["detection"],
        "review_settings": prepared_import["review"]["review_settings"],
    }
    request.session.modified = True


def _review_settings_from_post(request):
    selected_columns = request.POST.getlist("display_columns")
    return {
        "unique_identifier_selection": request.POST.get("unique_identifier_selection", GENERATE_INTERNAL_ID),
        "name_column": request.POST.get("name_column", ""),
        "major_column": request.POST.get("major_column", ""),
        "email_column": request.POST.get("email_column", ""),
        "timestamp_column": request.POST.get("timestamp_column", ""),
        "display_columns": selected_columns,
        "searchable_columns": selected_columns[:],
    }


def _build_review_context(pending_import, review_settings=None):
    review = build_import_review(
        pending_import["headers"],
        pending_import["rows"],
        pending_import["detection"],
        review_settings or pending_import.get("review_settings"),
    )
    pending_import["review_settings"] = review["review_settings"]

    mapping_fields = []
    for field_name in ("name", "major", "email", "timestamp"):
        mapping_fields.append(
            {
                "name": field_name,
                "label": FIELD_LABELS[field_name],
                "selected_header": review["review_settings"].get(f"{field_name}_column", ""),
            }
        )

    return {
        "detected_columns": review["detected_columns"],
        "header_count": review["header_count"],
        "identifier_label": review["identifier_label"],
        "identifier_options": review["identifier_options"],
        "review_settings": review["review_settings"],
        "mapping_fields": mapping_fields,
        "preview": review["preview"],
        "header_row_number": pending_import["header_row_number"],
        "has_name_timestamp_option": any(
            option["value"] == NAME_TIMESTAMP_ID for option in review["identifier_options"]
        ),
    }


def dashboard_view(request):
    try:
        registered_summary = RegisteredParticipant.objects.aggregate(
            total_rsvp=Count("id"),
            registered_checked_in=Count("id", filter=Q(checked_in=True)),
        )
        total_rsvp = registered_summary["total_rsvp"] or 0
        registered_checked_in = registered_summary["registered_checked_in"] or 0
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


@ensure_csrf_cookie
def registered_checkin_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    participants = list(
        RegisteredParticipant.objects.only(*REGISTERED_PARTICIPANT_LIST_FIELDS).order_by(
            "submission_order",
            "id",
        )
    )
    configuration = get_import_configuration_snapshot()
    checked_in_total = _count_checked_in(participants)
    context = {
        "active_nav": "registered",
        "participants": participants,
        "participant_table": _build_participant_table_context(participants, configuration),
        "registered_total": len(participants),
        "checked_in_total": checked_in_total,
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
        "summary": _pop_import_summary(request),
    }

    if request.method == "POST":
        uploaded_file = request.FILES.get("rsvp_file")
        prepared_import = prepare_rsvp_import(uploaded_file)
        if prepared_import["errors"]:
            context["summary"] = {
                "imported_count": 0,
                "skipped_count": 0,
                "duplicate_identifiers": [],
                "errors": prepared_import["errors"],
                "identifier_label": "Unique Identifier",
            }
        else:
            _save_pending_import(request, prepared_import)
            return redirect("checkin:import_rsvp_review")
    elif request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    participants = list(
        RegisteredParticipant.objects.only(*REGISTERED_PARTICIPANT_LIST_FIELDS).order_by(
            "submission_order",
            "id",
        )
    )
    guest_participants = list(
        GuestParticipant.objects.only(*GUEST_PARTICIPANT_LIST_FIELDS).order_by(
            "-checkin_time",
            "-created_at",
            "id",
        )
    )
    configuration = get_import_configuration_snapshot()

    context["participants"] = participants
    context["participant_table"] = _build_participant_table_context(participants, configuration)
    context["guest_participants"] = guest_participants
    context["registered_total"] = len(participants)
    context["registered_checked_in"] = _count_checked_in(participants)
    context["guest_count"] = len(guest_participants)
    context["pending_import_ready"] = bool(_pending_import_payload(request))
    return render(request, "import_rsvp.html", context)


def import_rsvp_review_view(request):
    pending_import = _pending_import_payload(request)
    if not pending_import:
        request.session[IMPORT_RESULT_SESSION_KEY] = {
            "imported_count": 0,
            "skipped_count": 0,
            "duplicate_identifiers": [],
            "errors": ["Upload an RSVP file before opening the import review step."],
            "identifier_label": "Unique Identifier",
        }
        request.session.modified = True
        return redirect("checkin:import_rsvp")

    if request.method == "POST":
        action = request.POST.get("review_action", "update")
        if action == "cancel":
            request.session.pop(IMPORT_SESSION_KEY, None)
            request.session.modified = True
            return redirect("checkin:import_rsvp")

        review_settings = _review_settings_from_post(request)
        review_context = _build_review_context(pending_import, review_settings)
        request.session[IMPORT_SESSION_KEY] = pending_import
        request.session.modified = True

        if action == "confirm":
            summary = import_rsvp_rows(
                pending_import["rows"],
                pending_import["headers"],
                pending_import["detection"],
                review_context["review_settings"],
            )
            request.session.pop(IMPORT_SESSION_KEY, None)
            request.session[IMPORT_RESULT_SESSION_KEY] = summary
            request.session.modified = True
            return redirect("checkin:import_rsvp")
    elif request.method == "GET":
        review_context = _build_review_context(pending_import)
        request.session[IMPORT_SESSION_KEY] = pending_import
        request.session.modified = True
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    context = {
        "active_nav": "data_tools",
        "review_context": review_context,
    }
    return render(request, "import_rsvp_review.html", context)


def export_attendance_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    return build_attendance_csv_response()


def export_rsvp_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    return build_rsvp_csv_response()


def export_rsvp_xlsx_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    return build_rsvp_xlsx_response()


def toggle_checkin(request, participant_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    participant = get_object_or_404(RegisteredParticipant, pk=participant_id)
    participant.checked_in = not participant.checked_in
    participant.checkin_time = timezone.now() if participant.checked_in else None
    participant.save(update_fields=["checked_in", "checkin_time", "updated_at"])

    if request.headers.get("HX-Request"):
        checked_in_total = RegisteredParticipant.objects.filter(checked_in=True).count()
        toggle_view = request.POST.get("toggle_view")
        template_name = "checkin/partials/checkin_button.html"
        if toggle_view == "import":
            template_name = "checkin/partials/import_checkin_button.html"
        return render(
            request,
            template_name,
            {
                "participant": participant,
                "checked_in_total": checked_in_total,
                "is_htmx": True,
            },
        )

    return _redirect_to_next(request, "checkin:registered_checkin")


def check_unid(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    unid = request.GET.get("unid", "").strip().lower()
    if not unid:
        return HttpResponse("")

    in_rsvp = RegisteredParticipant.objects.filter(unid__iexact=unid).first()
    in_guest = GuestParticipant.objects.filter(unid__iexact=unid).first()

    if not in_rsvp and not in_guest:
        return HttpResponse("")

    return render(
        request,
        "checkin/partials/unid_check.html",
        {
            "in_rsvp": in_rsvp,
            "in_guest": in_guest,
        },
    )


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


def analytics_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    try:
        configuration = get_import_configuration_snapshot()
        selected_columns = (
            configuration.get("display_columns")
            or configuration.get("imported_columns")
            or []
        )
        checked_in_registered = list(
            RegisteredParticipant.objects.only(*REGISTERED_PARTICIPANT_LIST_FIELDS).filter(
                checked_in=True,
                checkin_time__isnull=False,
            ).order_by("submission_order", "id")
        )
        checked_in_guests = list(
            GuestParticipant.objects.only(*GUEST_PARTICIPANT_LIST_FIELDS).filter(
                checked_in=True,
                checkin_time__isnull=False,
            ).order_by("-checkin_time", "-created_at", "id")
        )

        quarter_counts = defaultdict(int)
        for participant in checked_in_registered:
            dt = participant.checkin_time
            key = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
            quarter_counts[key] += 1
        for guest in checked_in_guests:
            dt = guest.checkin_time
            key = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
            quarter_counts[key] += 1

        sorted_quarters = sorted(quarter_counts)
        checkin_time_labels = [f"{q.hour:02d}:{q.minute:02d}" for q in sorted_quarters]
        checkin_time_values = [quarter_counts[q] for q in sorted_quarters]

        attendance_group_label, grouped_attendance = build_current_attendance_group_rows(
            checked_in_registered,
            checked_in_guests,
            selected_columns,
            configuration,
        )
        major_labels = [name for name, _ in grouped_attendance]
        major_values = [count for _, count in grouped_attendance]

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
            "major_labels": json.dumps(major_labels),
            "major_values": json.dumps(major_values),
            "attendance_group_label": attendance_group_label,
            "total_registered": total_registered,
            "total_checked_in": total_checked_in,
            "total_guest": total_guest,
            "has_checkin_data": bool(sorted_quarters),
            "has_major_data": bool(major_labels),
        }
    except (OperationalError, ProgrammingError):
        context = {
            "active_nav": "analytics",
            "checkin_time_labels": json.dumps([]),
            "checkin_time_values": json.dumps([]),
            "major_labels": json.dumps([]),
            "major_values": json.dumps([]),
            "attendance_group_label": "Major",
            "total_registered": 0,
            "total_checked_in": 0,
            "total_guest": 0,
            "has_checkin_data": False,
            "has_major_data": False,
        }

    return render(request, "checkin/analytics.html", context)
