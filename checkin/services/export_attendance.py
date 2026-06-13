import csv
import io
import re

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from checkin.models import GuestParticipant, RSVPImportConfiguration, RegisteredParticipant
from checkin.services.import_rsvp import build_participant_answers, get_import_configuration_snapshot


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

NOTE_COLUMN_CANDIDATES = (
    "notes",
    "note",
    "comments",
    "comment",
    "remarks",
    "remark",
    "special request",
    "special requests",
)

GROUPING_COLUMN_CANDIDATES = (
    "table",
    "team",
    "original team",
    "group",
    "role",
)

XLSX_EXPORT_FILENAME = "full_attendance_report.xlsx"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER_FONT = Font(bold=True)
FALLBACK_EVENT_NAME = "Spring 2026 RSVP Check-In System"


def _format_checkin_time(value):
    return value.isoformat(sep=" ", timespec="seconds") if value else ""


def _format_percentage(numerator, denominator):
    if not denominator:
        return "0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _format_column_list(columns):
    return ", ".join(columns) if columns else "None"


def _normalize_label(value):
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[/_-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(normalized.split())


def _dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _get_event_name():
    for setting_name in ("CHECKIN_EVENT_NAME", "RSVP_EVENT_NAME", "EVENT_NAME"):
        value = getattr(settings, setting_name, "")
        if value:
            return value
    return FALLBACK_EVENT_NAME


def _resolve_rsvp_export_columns(participants, configuration_snapshot, configuration):
    if configuration and configuration.display_columns:
        return configuration_snapshot.get("display_columns", [])

    answer_keys = _collect_answer_keys(participants)
    if answer_keys:
        return answer_keys

    return configuration_snapshot.get("display_columns") or configuration_snapshot.get("imported_columns") or [
        "Name",
        "UNID",
        "Major",
    ]


def _resolve_searchable_columns(configuration_snapshot, configuration, export_columns):
    if configuration and configuration.searchable_columns:
        return configuration_snapshot.get("searchable_columns", [])
    return export_columns


def _collect_answer_keys(participants, preferred_columns=None):
    columns = []
    seen = set()

    for column in preferred_columns or []:
        cleaned = str(column or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            columns.append(cleaned)

    for participant in participants:
        for key in (participant.answers or {}).keys():
            cleaned = str(key or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                columns.append(cleaned)

    return columns


def _resolve_raw_import_columns(participants, configuration_snapshot):
    raw_columns = _collect_answer_keys(
        participants,
        preferred_columns=configuration_snapshot.get("imported_columns") or configuration_snapshot.get("display_columns"),
    )
    if raw_columns:
        return raw_columns

    return ["Name", "UNID", "Major", "Email"]


def _get_answer_value(answers, column_name):
    return answers.get(column_name, "") if column_name else ""


def _get_rsvp_name(participant, answers, configuration_snapshot):
    configured_name_column = configuration_snapshot.get("name_column")
    if configured_name_column and answers.get(configured_name_column):
        return answers[configured_name_column]
    return answers.get("Name") or participant.name or ""


def _extract_notes_value(answers):
    for key, value in answers.items():
        normalized_key = _normalize_label(key)
        if any(candidate in normalized_key for candidate in NOTE_COLUMN_CANDIDATES):
            cleaned = str(value or "").strip()
            if cleaned:
                return cleaned
    return ""


def _guess_guest_value_for_column(column_name, guest):
    normalized = _normalize_label(column_name)
    if "name" in normalized:
        return guest.name
    if any(token in normalized for token in ("unid", "student id", "uid", "id", "identifier")):
        return guest.unid
    if any(token in normalized for token in ("major", "department", "program", "affiliation")):
        return guest.major
    return ""


def _build_all_attendance_headers(export_columns):
    return [
        "Source",
        "Record Type",
        "Unique Identifier",
        "Name",
        *export_columns,
        "Check-In Status",
        "Checked-In At",
        "Imported At / Created At",
        "Notes",
    ]


def _build_rsvp_only_headers(export_columns):
    return [
        "Unique Identifier",
        "Name",
        *export_columns,
        "Check-In Status",
        "Checked-In At",
        "Imported At",
    ]


def _build_guest_headers():
    return [
        "Source",
        "Record Type",
        "Guest Name",
        "Guest UNID",
        "Email",
        "Major",
        "Checked-In Status",
        "Checked-In At",
        "Created At",
        "Notes",
    ]


def _build_raw_import_headers(raw_columns):
    return [
        "Unique Identifier",
        *raw_columns,
        "Check-In Status",
        "Checked-In At",
        "Imported At",
    ]


def _build_all_attendance_rsvp_row(participant, export_columns, configuration_snapshot):
    answers = build_participant_answers(participant, configuration_snapshot)
    return [
        "Imported RSVP",
        "RSVP",
        participant.unid,
        _get_rsvp_name(participant, answers, configuration_snapshot),
        *[_get_answer_value(answers, column) for column in export_columns],
        "Checked In" if participant.checked_in else "Pending",
        _format_checkin_time(participant.checkin_time),
        _format_checkin_time(participant.created_at),
        _extract_notes_value(answers),
    ]


def _build_all_attendance_guest_row(guest, export_columns):
    return [
        "Guest Check-in",
        "Guest",
        guest.unid,
        guest.name,
        *[_guess_guest_value_for_column(column, guest) for column in export_columns],
        "Checked In" if guest.checked_in else "Pending",
        _format_checkin_time(guest.checkin_time),
        _format_checkin_time(guest.created_at),
        "",
    ]


def _build_rsvp_only_row(participant, export_columns, configuration_snapshot):
    answers = build_participant_answers(participant, configuration_snapshot)
    return [
        participant.unid,
        _get_rsvp_name(participant, answers, configuration_snapshot),
        *[_get_answer_value(answers, column) for column in export_columns],
        "Checked In" if participant.checked_in else "Pending",
        _format_checkin_time(participant.checkin_time),
        _format_checkin_time(participant.created_at),
    ]


def _build_guest_row(guest):
    return [
        "Guest Check-in",
        "Guest",
        guest.name,
        guest.unid,
        "",
        guest.major,
        "Checked In" if guest.checked_in else "Pending",
        _format_checkin_time(guest.checkin_time),
        _format_checkin_time(guest.created_at),
        "",
    ]


def _build_raw_import_row(participant, raw_columns, configuration_snapshot):
    answers = build_participant_answers(participant, configuration_snapshot)
    return [
        participant.unid,
        *[_get_answer_value(answers, column) for column in raw_columns],
        "Checked In" if participant.checked_in else "Pending",
        _format_checkin_time(participant.checkin_time),
        _format_checkin_time(participant.created_at),
    ]


def _detect_grouping_column(participants, configuration_snapshot):
    candidate_columns = _collect_answer_keys(
        participants,
        preferred_columns=configuration_snapshot.get("imported_columns") or configuration_snapshot.get("display_columns"),
    )
    normalized_pairs = [(column, _normalize_label(column)) for column in candidate_columns]

    for candidate in GROUPING_COLUMN_CANDIDATES:
        for column, normalized in normalized_pairs:
            if candidate in normalized:
                return column

    return ""


def _style_header_row(worksheet):
    for cell in worksheet[1]:
        cell.font = HEADER_FONT


def _autosize_columns(worksheet):
    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = get_column_letter(column_cells[0].column)
        for cell in column_cells:
            value_length = len(str(cell.value or ""))
            if value_length > max_length:
                max_length = value_length
        worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 48)


def _finalize_data_sheet(worksheet):
    _style_header_row(worksheet)
    worksheet.freeze_panes = "A2"
    _autosize_columns(worksheet)


def _add_summary_sheet(workbook, participants, guest_participants, configuration, configuration_snapshot, export_columns):
    worksheet = workbook.create_sheet("Summary")
    total_rsvp_records = len(participants)
    checked_in_rsvp = sum(1 for participant in participants if participant.checked_in)
    pending_rsvp = total_rsvp_records - checked_in_rsvp
    total_guest_checkins = len(guest_participants)
    total_actual_attendance = checked_in_rsvp + total_guest_checkins
    searchable_columns = _resolve_searchable_columns(
        configuration_snapshot,
        configuration,
        export_columns,
    )
    configuration_label = f"ID {configuration.id}" if configuration else "Not available"

    summary_rows = [
        ("Metric", "Value"),
        ("Event name", _get_event_name()),
        ("Export generated timestamp", _format_checkin_time(timezone.localtime())),
        ("Total imported RSVP records", total_rsvp_records),
        ("Total checked-in RSVP participants", checked_in_rsvp),
        ("Total RSVP not checked in / pending", pending_rsvp),
        ("Total guest check-ins", total_guest_checkins),
        ("Total actual attendance", total_actual_attendance),
        ("RSVP check-in rate", _format_percentage(checked_in_rsvp, total_rsvp_records)),
        ("Current import configuration", configuration_label),
        ("Unique identifier setting", configuration_snapshot.get("identifier_label", "Unique Identifier")),
        ("Dashboard display columns", _format_column_list(export_columns)),
        ("Searchable columns", _format_column_list(searchable_columns)),
    ]

    for row in summary_rows:
        worksheet.append(row)

    _finalize_data_sheet(worksheet)


def _add_all_attendance_sheet(workbook, participants, guest_participants, export_columns, configuration_snapshot):
    worksheet = workbook.create_sheet("All Attendance Records")
    worksheet.append(_build_all_attendance_headers(export_columns))

    for participant in participants:
        worksheet.append(
            _build_all_attendance_rsvp_row(
                participant,
                export_columns,
                configuration_snapshot,
            )
        )

    for guest in guest_participants:
        worksheet.append(_build_all_attendance_guest_row(guest, export_columns))

    _finalize_data_sheet(worksheet)


def _add_rsvp_sheet(workbook, sheet_name, participants, export_columns, configuration_snapshot):
    worksheet = workbook.create_sheet(sheet_name)
    worksheet.append(_build_rsvp_only_headers(export_columns))

    for participant in participants:
        worksheet.append(
            _build_rsvp_only_row(
                participant,
                export_columns,
                configuration_snapshot,
            )
        )

    _finalize_data_sheet(worksheet)


def _add_guest_sheet(workbook, guest_participants):
    worksheet = workbook.create_sheet("Guest Check-ins")
    worksheet.append(_build_guest_headers())

    for guest in guest_participants:
        worksheet.append(_build_guest_row(guest))

    _finalize_data_sheet(worksheet)


def _add_table_team_summary_sheet(workbook, participants, configuration_snapshot):
    worksheet = workbook.create_sheet("Table Team Summary")
    grouping_column = _detect_grouping_column(participants, configuration_snapshot)

    if not grouping_column:
        worksheet.append(["Note"])
        worksheet.append(["No table/team column detected in imported RSVP answers."])
        _finalize_data_sheet(worksheet)
        return

    worksheet.append(
        [
            grouping_column,
            "Total Assigned RSVP",
            "RSVP Checked In",
            "RSVP Not Checked In",
            "Guest Added",
            "Attendance Rate",
        ]
    )

    grouped_counts = {}
    for participant in participants:
        answers = build_participant_answers(participant, configuration_snapshot)
        group_value = answers.get(grouping_column) or "Unassigned"
        stats = grouped_counts.setdefault(
            group_value,
            {"total": 0, "checked_in": 0},
        )
        stats["total"] += 1
        if participant.checked_in:
            stats["checked_in"] += 1

    for group_value in sorted(grouped_counts):
        stats = grouped_counts[group_value]
        pending_count = stats["total"] - stats["checked_in"]
        worksheet.append(
            [
                group_value,
                stats["total"],
                stats["checked_in"],
                pending_count,
                0,
                _format_percentage(stats["checked_in"], stats["total"]),
            ]
        )

    _finalize_data_sheet(worksheet)


def _add_raw_import_sheet(workbook, participants, configuration_snapshot):
    raw_columns = _resolve_raw_import_columns(participants, configuration_snapshot)
    worksheet = workbook.create_sheet("Raw Imported RSVP Data")
    worksheet.append(_build_raw_import_headers(raw_columns))

    for participant in participants:
        worksheet.append(
            _build_raw_import_row(
                participant,
                raw_columns,
                configuration_snapshot,
            )
        )

    _finalize_data_sheet(worksheet)


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


def build_rsvp_xlsx_response():
    participants = list(RegisteredParticipant.objects.all().order_by("submission_order", "id"))
    guest_participants = list(GuestParticipant.objects.all().order_by("-checkin_time", "-created_at", "id"))
    checked_in_participants = [participant for participant in participants if participant.checked_in]
    pending_participants = [participant for participant in participants if not participant.checked_in]

    configuration = RSVPImportConfiguration.objects.order_by("pk").first()
    configuration_snapshot = get_import_configuration_snapshot()
    export_columns = _resolve_rsvp_export_columns(
        participants,
        configuration_snapshot,
        configuration,
    )

    workbook = Workbook()
    workbook.remove(workbook.active)

    _add_summary_sheet(
        workbook,
        participants,
        guest_participants,
        configuration,
        configuration_snapshot,
        export_columns,
    )
    _add_all_attendance_sheet(
        workbook,
        participants,
        guest_participants,
        export_columns,
        configuration_snapshot,
    )
    _add_rsvp_sheet(
        workbook,
        "RSVP Checked In",
        checked_in_participants,
        export_columns,
        configuration_snapshot,
    )
    _add_rsvp_sheet(
        workbook,
        "RSVP Not Checked In",
        pending_participants,
        export_columns,
        configuration_snapshot,
    )
    _add_guest_sheet(workbook, guest_participants)
    _add_table_team_summary_sheet(workbook, participants, configuration_snapshot)
    _add_raw_import_sheet(workbook, participants, configuration_snapshot)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=XLSX_CONTENT_TYPE,
    )
    response["Content-Disposition"] = f'attachment; filename="{XLSX_EXPORT_FILENAME}"'
    return response
