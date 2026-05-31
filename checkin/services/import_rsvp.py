import csv
import io
import logging
import re
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Max

from checkin.models import RegisteredParticipant


logger = logging.getLogger(__name__)

IMPORT_SESSION_KEY = "pending_rsvp_import"
REQUIRED_FIELD_NAMES = ("name", "unid")
OPTIONAL_FIELD_NAMES = ("major",)
IMPORT_FIELD_NAMES = REQUIRED_FIELD_NAMES + OPTIONAL_FIELD_NAMES

FIELD_LABELS = {
    "name": "Name",
    "unid": "UNID",
    "major": "Major",
}

FIELD_ALIASES = {
    "name": {
        "name",
        "full name",
        "student name",
        "participant name",
        "attendee name",
        "first and last name",
        "your name",
        "what is your name",
        "legal name",
        "preferred name",
    },
    "unid": {
        "unid",
        "u nid",
        "student id",
        "student number",
        "university id",
        "university id number",
        "uid",
        "u id",
        "utah id",
        "campus id",
        "what is your unid",
    },
    "major": {
        "major",
        "major program",
        "program",
        "degree program",
        "field of study",
        "area of study",
        "department",
        "academic program",
        "concentration",
        "what is your major",
    },
}

HIGH_CONFIDENCE_THRESHOLD = 0.9
LOW_CONFIDENCE_THRESHOLD = 0.72
UNID_PATTERN = re.compile(r"^u\d{7}$")


def _normalize_header(value):
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[/_-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(normalized.split())


def _clean_cell(value):
    if value is None:
        return ""
    return str(value).strip()


def _clean_detected_headers(header_row):
    return [_clean_cell(header) for header in header_row if _clean_cell(header)]


def _score_header_for_field(header, field_name):
    normalized_header = _normalize_header(header)
    if not normalized_header:
        return 0

    aliases = FIELD_ALIASES[field_name]
    if normalized_header in aliases:
        return 1

    header_tokens = set(normalized_header.split())
    best_score = 0
    for alias in aliases:
        alias_tokens = set(alias.split())
        if not alias_tokens:
            continue
        if alias in normalized_header:
            best_score = max(best_score, 0.92)
        elif alias_tokens.issubset(header_tokens):
            best_score = max(best_score, 0.88)
        elif header_tokens.issubset(alias_tokens):
            best_score = max(best_score, 0.78)
        else:
            best_score = max(best_score, SequenceMatcher(None, normalized_header, alias).ratio())

    return round(best_score, 2)


def detect_column_mapping(headers):
    matches = {}
    used_headers = set()

    for field_name in IMPORT_FIELD_NAMES:
        scored_headers = sorted(
            (
                (_score_header_for_field(header, field_name), header)
                for header in headers
                if header not in used_headers
            ),
            reverse=True,
        )
        if not scored_headers:
            continue

        score, header = scored_headers[0]
        if score >= LOW_CONFIDENCE_THRESHOLD:
            matches[field_name] = {
                "header": header,
                "confidence": score,
                "label": FIELD_LABELS[field_name],
            }
            used_headers.add(header)

    missing_required = [field for field in REQUIRED_FIELD_NAMES if field not in matches]
    low_confidence_required = [
        field
        for field in REQUIRED_FIELD_NAMES
        if field in matches and matches[field]["confidence"] < HIGH_CONFIDENCE_THRESHOLD
    ]
    needs_mapping = bool(missing_required or low_confidence_required)

    return {
        "matches": matches,
        "missing_required": missing_required,
        "low_confidence_required": low_confidence_required,
        "needs_mapping": needs_mapping,
    }


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


def _parse_csv_file(uploaded_file):
    file_text = _decode_uploaded_file(uploaded_file)
    csv_buffer = io.StringIO(file_text, newline="")

    try:
        reader = csv.DictReader(csv_buffer)
    except csv.Error as error:
        raise ValueError(f"Could not read CSV file: {error}") from error

    if not reader.fieldnames:
        raise ValueError("The CSV file is missing a header row.")

    headers = _clean_detected_headers(reader.fieldnames)
    rows = []
    for row in reader:
        rows.append({header: _clean_cell(row.get(header)) for header in headers})
    return headers, rows


def _parse_xlsx_file(uploaded_file):
    try:
        from openpyxl import load_workbook
    except ImportError as error:
        raise ValueError("XLSX uploads require the openpyxl package to be installed.") from error

    uploaded_file.seek(0)
    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception as error:
        raise ValueError(f"Could not read XLSX file: {error}") from error

    worksheet = workbook.active
    rows = worksheet.iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration as error:
        raise ValueError("The XLSX file is empty.") from error

    headers = _clean_detected_headers(header_row)
    if not headers:
        raise ValueError("The XLSX file is missing a header row.")

    parsed_rows = []
    for values in rows:
        row = {}
        for index, header in enumerate(headers):
            row[header] = _clean_cell(values[index] if index < len(values) else "")
        if any(row.values()):
            parsed_rows.append(row)
    return headers, parsed_rows


def parse_rsvp_file(uploaded_file):
    if not uploaded_file:
        raise ValueError("Please choose a CSV or XLSX file to import.")

    file_name = (uploaded_file.name or "").lower()
    if file_name.endswith(".csv"):
        return _parse_csv_file(uploaded_file)
    if file_name.endswith(".xlsx"):
        return _parse_xlsx_file(uploaded_file)
    raise ValueError("Only CSV and XLSX uploads are supported.")


def _mapping_from_detection(detection):
    return {
        field: match["header"]
        for field, match in detection["matches"].items()
        if match.get("header")
    }


def _clean_mapping(mapping):
    return {
        field: (mapping.get(field) or "").strip()
        for field in IMPORT_FIELD_NAMES
        if (mapping.get(field) or "").strip()
    }


def _validate_mapping(mapping, headers):
    errors = []
    for field in REQUIRED_FIELD_NAMES:
        if not mapping.get(field):
            errors.append(f"{FIELD_LABELS[field]} must be mapped before import.")
        elif mapping[field] not in headers:
            errors.append(f"{FIELD_LABELS[field]} is mapped to an unknown column.")
    return errors


def build_import_preview(rows, mapping):
    mapping = _clean_mapping(mapping)
    existing_unids = {
        (unid or "").strip().lower()
        for unid in RegisteredParticipant.objects.values_list("unid", flat=True)
    }
    seen_unids_in_file = set()
    row_previews = []
    total_rows = len(rows)
    valid_count = 0
    invalid_count = 0
    missing_required_count = 0
    invalid_unid_count = 0
    duplicate_count = 0

    for index, row in enumerate(rows, start=2):
        name = _clean_cell(row.get(mapping.get("name", "")))
        unid = _clean_cell(row.get(mapping.get("unid", "")))
        major = _clean_cell(row.get(mapping.get("major", ""))) if mapping.get("major") else ""
        normalized_unid = unid.lower()
        row_errors = []

        missing_values = []
        if not name:
            missing_values.append("Name")
        if not unid:
            missing_values.append("UNID")
        if missing_values:
            row_errors.append("Missing required value(s): " + ", ".join(missing_values) + ".")
            missing_required_count += 1

        if unid and not UNID_PATTERN.match(normalized_unid):
            row_errors.append("UNID must be in the format u1234567.")
            invalid_unid_count += 1

        if normalized_unid and normalized_unid in existing_unids:
            row_errors.append("Duplicate UNID already exists.")
            duplicate_count += 1
        elif normalized_unid and normalized_unid in seen_unids_in_file:
            row_errors.append("Duplicate UNID in uploaded file.")
            duplicate_count += 1

        if row_errors:
            invalid_count += 1
        else:
            valid_count += 1
            seen_unids_in_file.add(normalized_unid)

        row_previews.append(
            {
                "row_number": index,
                "name": name,
                "unid": unid,
                "normalized_unid": normalized_unid,
                "major": major,
                "errors": row_errors,
                "is_valid": not row_errors,
            }
        )

    return {
        "total_rows": total_rows,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "missing_required_count": missing_required_count,
        "invalid_unid_count": invalid_unid_count,
        "duplicate_count": duplicate_count,
        "rows": row_previews,
        "preview_rows": row_previews[:5],
    }


def prepare_rsvp_import(uploaded_file, mapping=None):
    result = {
        "headers": [],
        "rows": [],
        "mapping": {},
        "detection": None,
        "preview": None,
        "errors": [],
    }

    try:
        headers, rows = parse_rsvp_file(uploaded_file)
    except ValueError as error:
        result["errors"].append(str(error))
        return result

    detection = detect_column_mapping(headers)
    selected_mapping = _clean_mapping(mapping or _mapping_from_detection(detection))
    if mapping is None and detection["missing_required"]:
        missing_labels = [FIELD_LABELS[field] for field in detection["missing_required"]]
        error_message = "Missing required column(s): " + ", ".join(missing_labels)
        if headers:
            error_message += ". Detected column(s): " + ", ".join(headers)
        result.update(
            {
                "headers": headers,
                "rows": rows,
                "mapping": selected_mapping,
                "detection": detection,
            }
        )
        result["errors"].append(error_message)
        return result

    mapping_errors = _validate_mapping(selected_mapping, headers)

    result.update(
        {
            "headers": headers,
            "rows": rows,
            "mapping": selected_mapping,
            "detection": detection,
        }
    )

    if mapping_errors:
        result["errors"].extend(mapping_errors)
        return result

    result["preview"] = build_import_preview(rows, selected_mapping)
    return result


def import_rsvp_rows(rows, mapping):
    summary = {
        "imported_count": 0,
        "skipped_count": 0,
        "duplicate_unids": [],
        "errors": [],
        "total_rows": len(rows),
        "valid_count": 0,
        "invalid_count": 0,
        "missing_required_count": 0,
        "invalid_unid_count": 0,
    }
    mapping = _clean_mapping(mapping)
    headers = list(rows[0].keys()) if rows else list(mapping.values())
    mapping_errors = _validate_mapping(mapping, headers)
    if mapping_errors:
        summary["errors"].extend(mapping_errors)
        summary["skipped_count"] = len(rows)
        summary["invalid_count"] = len(rows)
        return summary

    existing_unids = {
        (unid or "").strip().lower()
        for unid in RegisteredParticipant.objects.values_list("unid", flat=True)
    }
    seen_unids_in_file = set()
    next_submission_order = (
        RegisteredParticipant.objects.aggregate(max_order=Max("submission_order"))["max_order"] or 0
    )
    participants_to_create = []

    for row_number, row in enumerate(rows, start=2):
        name = _clean_cell(row.get(mapping["name"]))
        unid = _clean_cell(row.get(mapping["unid"]))
        major = _clean_cell(row.get(mapping.get("major", ""))) if mapping.get("major") else ""
        normalized_unid = unid.lower()

        missing_values = []
        if not name:
            missing_values.append("Name")
        if not unid:
            missing_values.append("UNID")

        if missing_values:
            summary["skipped_count"] += 1
            summary["missing_required_count"] += 1
            summary["errors"].append(
                f"Row {row_number}: missing required value(s): {', '.join(missing_values)}."
            )
            continue

        if not UNID_PATTERN.match(normalized_unid):
            summary["skipped_count"] += 1
            summary["invalid_unid_count"] += 1
            summary["errors"].append(
                f"Row {row_number} skipped: UNID must be in the format u1234567."
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
    summary["valid_count"] = len(participants_to_create)
    summary["invalid_count"] = summary["skipped_count"]
    return summary


def import_rsvp_file(uploaded_file, mapping=None):
    summary = {
        "imported_count": 0,
        "skipped_count": 0,
        "duplicate_unids": [],
        "errors": [],
        "total_rows": 0,
        "valid_count": 0,
        "invalid_count": 0,
        "missing_required_count": 0,
        "invalid_unid_count": 0,
    }

    prepared_import = prepare_rsvp_import(uploaded_file, mapping=mapping)
    if prepared_import["errors"]:
        summary["errors"].extend(prepared_import["errors"])
        return summary

    logger.debug("Detected RSVP import headers: %s", prepared_import["headers"])
    logger.debug("Matched RSVP import headers: %s", prepared_import["mapping"])
    return import_rsvp_rows(prepared_import["rows"], prepared_import["mapping"])
