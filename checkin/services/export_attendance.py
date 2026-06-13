import csv
import io

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

XLSX_EXPORT_FILENAME = "rsvp_data_export.xlsx"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER_FONT = Font(bold=True)


def _format_checkin_time(value):
    return value.isoformat(sep=" ", timespec="seconds") if value else ""


def _format_percentage(numerator, denominator):
    if not denominator:
        return "0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _format_column_list(columns):
    return ", ".join(columns) if columns else "None"


def _resolve_rsvp_export_columns(participants, configuration_snapshot, configuration):
    if configuration and configuration.display_columns:
        return configuration_snapshot.get("display_columns", [])

    answer_keys = []
    seen = set()
    for participant in participants:
        for key in (participant.answers or {}).keys():
            if key and key not in seen:
                seen.add(key)
                answer_keys.append(key)

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


def _build_rsvp_export_headers(export_columns):
    return [
        "Unique Identifier",
        *export_columns,
        "Check-In Status",
        "Checked-In At",
        "Imported At",
    ]


def _build_rsvp_export_row(participant, export_columns, configuration_snapshot):
    answers = build_participant_answers(participant, configuration_snapshot)
    return [
        participant.unid,
        *[answers.get(column, "") for column in export_columns],
        "Checked In" if participant.checked_in else "Not Checked In",
        _format_checkin_time(participant.checkin_time),
        _format_checkin_time(participant.created_at),
    ]


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


def _add_summary_sheet(workbook, participants, configuration, configuration_snapshot, export_columns):
    worksheet = workbook.create_sheet("Summary")
    total_records = len(participants)
    checked_in_count = sum(1 for participant in participants if participant.checked_in)
    not_checked_in_count = total_records - checked_in_count
    searchable_columns = _resolve_searchable_columns(
        configuration_snapshot,
        configuration,
        export_columns,
    )

    configuration_label = f"ID {configuration.id}" if configuration else "Not available"
    summary_rows = [
        ("Metric", "Value"),
        ("Total RSVP records", total_records),
        ("Checked-in count", checked_in_count),
        ("Not checked-in count", not_checked_in_count),
        ("Check-in rate", _format_percentage(checked_in_count, total_records)),
        ("Export generated timestamp", _format_checkin_time(timezone.localtime())),
        ("Current import configuration ID", configuration_label),
        ("Unique identifier column setting", configuration_snapshot.get("identifier_label", "Unique Identifier")),
        ("Dashboard display columns", _format_column_list(export_columns)),
        ("Searchable columns", _format_column_list(searchable_columns)),
    ]

    for row in summary_rows:
        worksheet.append(row)

    _style_header_row(worksheet)
    worksheet.freeze_panes = "A2"
    _autosize_columns(worksheet)


def _add_rsvp_data_sheet(workbook, sheet_name, participants, export_columns, configuration_snapshot):
    worksheet = workbook.create_sheet(sheet_name)
    worksheet.append(_build_rsvp_export_headers(export_columns))
    _style_header_row(worksheet)
    worksheet.freeze_panes = "A2"

    for participant in participants:
        worksheet.append(
            _build_rsvp_export_row(
                participant,
                export_columns,
                configuration_snapshot,
            )
        )

    _autosize_columns(worksheet)


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
    checked_in_participants = [participant for participant in participants if participant.checked_in]
    not_checked_in_participants = [participant for participant in participants if not participant.checked_in]

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
        configuration,
        configuration_snapshot,
        export_columns,
    )
    _add_rsvp_data_sheet(
        workbook,
        "All RSVP Records",
        participants,
        export_columns,
        configuration_snapshot,
    )
    _add_rsvp_data_sheet(
        workbook,
        "Checked In",
        checked_in_participants,
        export_columns,
        configuration_snapshot,
    )
    _add_rsvp_data_sheet(
        workbook,
        "Not Checked In",
        not_checked_in_participants,
        export_columns,
        configuration_snapshot,
    )

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=XLSX_CONTENT_TYPE,
    )
    response["Content-Disposition"] = f'attachment; filename="{XLSX_EXPORT_FILENAME}"'
    return response
