import csv
import io

from django.db import transaction
from django.db.models import Max

from checkin.models import RegisteredParticipant


REQUIRED_FIELDS = {
    "name": {"name", "full name"},
    "unid": {"unid", "uni", "student id", "university id"},
    "major": {"major", "program", "department"},
}


def _normalize_header(value):
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _match_headers(header_row):
    matched_headers = {}
    normalized_headers = {
        _normalize_header(header): header for header in header_row if header is not None
    }

    for field_name, aliases in REQUIRED_FIELDS.items():
        for normalized_header, original_header in normalized_headers.items():
            if normalized_header in aliases:
                matched_headers[field_name] = original_header
                break

    missing_fields = [field for field in REQUIRED_FIELDS if field not in matched_headers]
    return matched_headers, missing_fields


def _decode_uploaded_file(uploaded_file):
    uploaded_file.seek(0)
    raw_content = uploaded_file.read()

    if isinstance(raw_content, str):
        return raw_content

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("The uploaded file could not be decoded as text.")


def import_rsvp_file(uploaded_file):
    summary = {
        "imported_count": 0,
        "skipped_count": 0,
        "duplicate_unids": [],
        "errors": [],
    }

    if not uploaded_file:
        summary["errors"].append("Please choose a CSV file to import.")
        return summary

    file_name = (uploaded_file.name or "").lower()
    if not file_name.endswith(".csv"):
        summary["errors"].append("Only CSV uploads are supported right now.")
        return summary

    try:
        file_text = _decode_uploaded_file(uploaded_file)
    except ValueError as error:
        summary["errors"].append(str(error))
        return summary

    csv_buffer = io.StringIO(file_text, newline="")

    try:
        reader = csv.DictReader(csv_buffer)
    except csv.Error as error:
        summary["errors"].append(f"Could not read CSV file: {error}")
        return summary

    if not reader.fieldnames:
        summary["errors"].append("The CSV file is missing a header row.")
        return summary

    matched_headers, missing_fields = _match_headers(reader.fieldnames)
    if missing_fields:
        summary["errors"].append(
            "Missing required column(s): " + ", ".join(field.title() for field in missing_fields)
        )
        return summary

    existing_unids = set(
        RegisteredParticipant.objects.values_list("unid", flat=True)
    )
    seen_unids_in_file = set()
    next_submission_order = (
        RegisteredParticipant.objects.aggregate(max_order=Max("submission_order"))["max_order"] or 0
    )
    participants_to_create = []

    for csv_row_number, row in enumerate(reader, start=2):
        name = (row.get(matched_headers["name"]) or "").strip()
        unid = (row.get(matched_headers["unid"]) or "").strip()
        major = (row.get(matched_headers["major"]) or "").strip()

        missing_values = []
        if not name:
            missing_values.append("Name")
        if not unid:
            missing_values.append("UNID")
        if not major:
            missing_values.append("Major")

        if missing_values:
            summary["skipped_count"] += 1
            summary["errors"].append(
                f"Row {csv_row_number}: missing required value(s): {', '.join(missing_values)}."
            )
            continue

        if unid in existing_unids or unid in seen_unids_in_file:
            summary["skipped_count"] += 1
            if unid not in summary["duplicate_unids"]:
                summary["duplicate_unids"].append(unid)
            continue

        next_submission_order += 1
        seen_unids_in_file.add(unid)
        participants_to_create.append(
            RegisteredParticipant(
                submission_order=next_submission_order,
                name=name,
                unid=unid,
                major=major,
            )
        )

    try:
        with transaction.atomic():
            RegisteredParticipant.objects.bulk_create(participants_to_create)
    except Exception as error:
        summary["errors"].append(f"Import failed while saving rows: {error}")
        return summary

    summary["imported_count"] = len(participants_to_create)
    return summary
