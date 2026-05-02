import csv
import io
import logging
import re

from django.db import transaction
from django.db.models import Max

from checkin.models import RegisteredParticipant


logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "name": {"name", "full name"},
    "unid": {"unid", "uni", "student id", "university id"},
    "major": {"major", "program", "department"},
}

REQUIRED_FIELD_LABELS = {
    "name": "Name",
    "unid": "UNID",
    "major": "Major",
}

UNID_PATTERN = re.compile(r"^u\d{7}$")


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


def _clean_detected_headers(header_row):
    return [str(header).strip() for header in header_row if str(header or "").strip()]


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

    detected_headers = _clean_detected_headers(reader.fieldnames)
    logger.debug("Detected RSVP import headers: %s", detected_headers)

    matched_headers, missing_fields = _match_headers(reader.fieldnames)
    if missing_fields:
        missing_labels = [REQUIRED_FIELD_LABELS[field] for field in missing_fields]
        error_message = "Missing required column(s): " + ", ".join(missing_labels)
        if detected_headers:
            error_message += ". Detected column(s): " + ", ".join(detected_headers)
        summary["errors"].append(
            error_message
        )
        return summary

    logger.debug(
        "Matched RSVP import headers: %s",
        {field: matched_headers[field] for field in REQUIRED_FIELDS},
    )

    existing_unids = {
        (unid or "").strip().lower()
        for unid in RegisteredParticipant.objects.values_list("unid", flat=True)
    }
    seen_unids_in_file = set()
    next_submission_order = (
        RegisteredParticipant.objects.aggregate(max_order=Max("submission_order"))["max_order"] or 0
    )
    participants_to_create = []

    for csv_row_number, row in enumerate(reader, start=2):
        name = (row.get(matched_headers["name"]) or "").strip()
        unid = (row.get(matched_headers["unid"]) or "").strip()
        major = (row.get(matched_headers["major"]) or "").strip()
        normalized_unid = unid.lower()

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

        if not UNID_PATTERN.match(normalized_unid):
            summary["skipped_count"] += 1
            summary["errors"].append(
                f"Row {csv_row_number} skipped: UNID must be in the format u1234567."
            )
            continue

        if normalized_unid in existing_unids or normalized_unid in seen_unids_in_file:
            summary["skipped_count"] += 1
            if normalized_unid not in summary["duplicate_unids"]:
                summary["duplicate_unids"].append(normalized_unid)
            continue

        next_submission_order += 1
        seen_unids_in_file.add(normalized_unid)
        participants_to_create.append(
            RegisteredParticipant(
                submission_order=next_submission_order,
                name=name,
                unid=normalized_unid,
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
