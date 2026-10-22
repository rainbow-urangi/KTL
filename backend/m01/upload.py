# CSV 업로드 및 검사·저장
import base64
import binascii
import csv
import hashlib
import io
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from ..evaluators import EvaluationError, require
from ..run_storage import save_run


MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_EVENT_ROWS = 100000
CSV_VERSION = "m01-csv-diagnostic-v3"
LEGACY_MAPPING_VERSION = "collector-events-to-ktl-types-v2"
MAPPING_VERSION = "collector-events-to-ktl-types-v3"
TEXT_INPUT_TYPES = frozenset({"text", "search", "email", "url", "tel", "password", "number"})
REQUIRED_FIELDS = ("session_id", "event_time", "event_type", "page_url", "page_title", "target_key")
EVENT_TYPES = {
    "navigation": "화면 이동", "click": "클릭", "input": "입력",
    "select_change": "선택/변경", "submit_save": "제출/저장", "popup": "팝업",
    "network": "네트워크 요청", "key_input": "키 입력",
}
TYPE_MAPPING = {
    "page_view": "navigation", "route_change": "navigation", "navigation": "navigation",
    "click": "click", "grid_cell_click": "click", "gridcell": "click",
    "input": "input", "paste": "input", "change": "select_change", "select": "select_change",
    "submit": "submit_save", "save": "submit_save",
    "popup_open": "popup", "popup_close": "popup",
    "api_transaction": "network", "fetch_request": "network", "xhr_request": "network",
    "keydown": "key_input",
}


def parse_csv(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_CSV_BYTES,
            "CSV file required; maximum 10 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise EvaluationError("CSV must be UTF-8 (UTF-8 BOM is supported)")
    require("\x00" not in text, "CSV contains a NUL character")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, [])
        require(headers and all(name and name == name.strip() for name in headers),
                "CSV header names must be nonempty and have no surrounding whitespace")
        require(len(headers) == len(set(headers)), "Duplicate CSV header names")
        require(any(name in headers for name in ("event_id", "session_id", "event_time", "event_type")),
                "Collector event CSV header required (case-sensitive)")
        rows = []
        for values in reader:
            require(len(values) == len(headers), "CSV row has a different field count from its header")
            require(len(rows) < MAX_EVENT_ROWS, "CSV maximum is 100000 event rows; split the file into collection sessions")
            rows.append(dict(zip(headers, values)))
    except csv.Error:
        raise EvaluationError("Malformed CSV or field exceeds CSV parser limit")
    require(rows, "CSV contains no event rows")
    return headers, rows


def category(row, mapping_version=MAPPING_VERSION):
    require(mapping_version in {LEGACY_MAPPING_VERSION, MAPPING_VERSION}, "Unsupported M01 type mapping version")
    event_type = row.get("event_type", "").strip().lower()
    interaction = row.get("interaction_type", "").strip().lower()
    if event_type in EVENT_TYPES:
        return event_type
    # DOM_EVENT 동작 분류 및 초기화·결과 이벤트 제외
    if event_type == "dom_event":
        if interaction == "change" and mapping_version == MAPPING_VERSION:
            tag = row.get("element_tag", "").strip().lower()
            control = row.get("input_control_type", "").strip().lower()
            if (tag == "textarea" and control == "textarea") or (tag == "input" and control in TEXT_INPUT_TYPES):
                return "input"
        return TYPE_MAPPING.get(interaction)
    return TYPE_MAPPING.get(event_type)


def missing_fields(row, map_target_selector=False):
    missing = []
    for name in REQUIRED_FIELDS:
        value = row.get(name, "")
        if name == "target_key" and not value.strip() and map_target_selector:
            value = row.get("target_selector", "")
        if not value.strip():
            missing.append(name)
    return missing


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def display(value):
    # 화면 표시값의 민감 정보 마스킹
    value = str(value or "")[:300]
    return re.sub(r"(?i)(password|passwd|token|authorization|cookie|secret)(\s*[=:]\s*)[^\s\]>'\"]+",
                  r"\1\2[REDACTED]", value)


def display_url(value):
    try:
        parts = urlsplit(value)
        netloc = parts.netloc.rsplit("@", 1)[-1]
        return display(urlunsplit((parts.scheme, netloc, parts.path, "", "")))
    except ValueError:
        return "[invalid URL]"


def preview_rows(indexed, ids, map_target_selector):
    for number, row in indexed:
        yield {
            "csv_row": number + 1, "event_id": display(row.get("event_id")),
            "session_id": display(row.get("session_id")), "event_time": display(row.get("event_time")),
            "event_type": display(row.get("event_type")), "interaction_type": display(row.get("interaction_type")),
            "ktl_type": category(row) or "unclassified", "page_url": display_url(row.get("page_url", "")),
            "page_title": display(row.get("page_title")), "target_selector": display(row.get("target_selector")),
            "missing_fields": ", ".join(missing_fields(row, map_target_selector)),
            "duplicate_event_id": bool(row.get("event_id", "").strip() and ids[row["event_id"].strip()] > 1),
        }


def diagnose(rows, headers, map_target_selector=False, session_id=None, offset=0, limit=100):
    require(type(map_target_selector) is bool, "map_target_selector must be a boolean")
    require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 200,
            "offset must be nonnegative; limit must be 1..200")
    indexed = [(number, row) for number, row in enumerate(rows, start=1)
               if session_id is None or row.get("session_id", "") == session_id]
    require(indexed, "No events in the selected session")
    selected = [row for _, row in indexed]
    raw_missing = Counter(name for row in selected for name in missing_fields(row))
    effective_missing = Counter(name for row in selected for name in missing_fields(row, map_target_selector))
    coverage = Counter(category(row) for row in selected)
    ids = Counter(row.get("event_id", "").strip() for row in selected if row.get("event_id", "").strip())
    times = [timestamp(row.get("event_time", "")) for row in selected]
    valid_times = [value for value in times if value is not None]
    session_counts = Counter(row.get("session_id", "") for row in rows)
    missing_count = sum(effective_missing.values())
    summary = {
        "source_event_count": len(rows), "event_count": len(selected), "session_count": len(session_counts),
        "sessions": [{"session_id": key, "event_count": count} for key, count in sorted(session_counts.items())],
        "scope": {"session_id": session_id, "description": "whole CSV" if session_id is None else "selected session"},
        "required_fields": list(REQUIRED_FIELDS), "missing_header_fields": [name for name in REQUIRED_FIELDS if name not in headers],
        "raw_missing_fields": dict(raw_missing), "raw_missing_field_count": sum(raw_missing.values()),
        "missing_fields": dict(effective_missing), "missing_field_count": missing_count,
        "required_field_slots": len(selected) * len(REQUIRED_FIELDS),
        "target_selector_mapping": map_target_selector, "mapping_version": MAPPING_VERSION,
        "type_counts": {key: coverage[key] for key in EVENT_TYPES},
        "missing_types": [key for key in EVENT_TYPES if not coverage[key]],
        "unclassified_event_count": coverage[None],
        "duplicate_event_id_rows": sum(count - 1 for count in ids.values()),
        "missing_event_id_rows": sum(not row.get("event_id", "").strip() for row in selected),
        "event_time_min_utc": min(valid_times) if valid_times else None,
        "event_time_max_utc": max(valid_times) if valid_times else None,
        "invalid_or_timezone_missing_event_times": len(times) - len(valid_times),
        "c1": None, "c2": missing_count / (len(selected) * len(REQUIRED_FIELDS)) * 100,
        "raw_c2": sum(raw_missing.values()) / (len(selected) * len(REQUIRED_FIELDS)) * 100,
        "c3": sum(bool(coverage[key]) for key in EVENT_TYPES) / len(EVENT_TYPES) * 100,
        "score": None, "official_pass": None,
        "pending": "TD-02 required-event definitions and matching are needed for C1 and final score",
    }
    preview = list(preview_rows(indexed[offset:offset + limit], ids, map_target_selector))
    return {"summary": summary, "rows": preview, "offset": offset, "limit": limit,
            "has_more": offset + limit < len(indexed)}


class M01CsvStore:
    def __init__(self, root):
        self.root = root
        self.directory = root / "data/development/m01_uploads"

    def upload(self, payload, config):
        require(isinstance(payload, dict), "JSON object required")
        require(set(payload) <= {"filename", "csv_base64", "map_target_selector"}, "Unexpected upload field")
        filename = payload.get("filename")
        encoded = payload.get("csv_base64")
        mapping = payload.get("map_target_selector", False)
        require(isinstance(filename, str) and 0 < len(filename) <= 255 and filename.lower().endswith(".csv")
                and "/" not in filename and "\\" not in filename and not any(ord(c) < 32 for c in filename),
                "A CSV filename without a path is required")
        require(isinstance(encoded, str) and len(encoded) <= ((MAX_CSV_BYTES + 2) // 3) * 4,
                "CSV base64 required; maximum file size 10 MiB")
        require(type(mapping) is bool, "map_target_selector must be a boolean")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise EvaluationError("Invalid CSV base64")
        headers, rows = parse_csv(raw)
        report = diagnose(rows, headers, mapping)
        dataset_id = uuid.uuid4().hex
        directory = self.directory / dataset_id
        directory.mkdir(parents=True, exist_ok=False)
        digest = hashlib.sha256(raw).hexdigest()
        manifest = {
            "dataset_id": dataset_id, "filename": filename, "run_mode": "DEVELOPMENT", "source_type": "collector_csv_upload",
            "uploaded_at": datetime.now(timezone.utc).isoformat(), "sha256": digest, "byte_count": len(raw),
            "headers": headers, "mapping_version": MAPPING_VERSION, "target_selector_mapping": mapping,
            "summary": report["summary"], "evaluator_version": CSV_VERSION,
        }
        (directory / "source.csv").write_bytes(raw)
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        evidence = [{"diagnostic": "C2", "value": report["summary"]["c2"]},
                    {"diagnostic": "C3", "value": report["summary"]["c3"]},
                    {"diagnostic": "C1", "value": "PENDING_REQUIRED_EVENT_DEFINITIONS"}]
        result = save_run(self.root, "M01", "DEVELOPMENT", config, {
            "status": "DEVELOPMENT_DIAGNOSTIC", "score": None, "sample_count": len(rows), "dataset_id": dataset_id,
            "source_type": "collector_csv_upload", "evaluator_version": CSV_VERSION,
            "input_sha256": {str((directory / "source.csv").relative_to(self.root)): digest},
            "details": {"csv_summary": report["summary"], "filename": filename, "mapping_version": MAPPING_VERSION},
        }, evidence)
        manifest["run_id"] = result["run_id"]
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(report, dataset=manifest, status="DEVELOPMENT_DIAGNOSTIC", run_mode="DEVELOPMENT")

    def read(self, dataset_id, **options):
        require(isinstance(dataset_id, str) and re.fullmatch(r"[0-9a-f]{32}", dataset_id), "Invalid dataset ID")
        directory = self.directory / dataset_id
        if not (directory / "manifest.json").is_file():
            raise EvaluationError("CSV dataset not found", "NOT_FOUND")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        raw = (directory / "source.csv").read_bytes()
        require(hashlib.sha256(raw).hexdigest() == manifest["sha256"], "Stored CSV hash mismatch")
        headers, rows = parse_csv(raw)
        options.setdefault("map_target_selector", manifest["target_selector_mapping"])
        report = diagnose(rows, headers, **options)
        return dict(report, dataset=manifest, status="DEVELOPMENT_DIAGNOSTIC", run_mode="DEVELOPMENT")

    def list(self):
        manifests = []
        if self.directory.exists():
            for path in self.directory.glob("*/manifest.json"):
                if re.fullmatch(r"[0-9a-f]{32}", path.parent.name):
                    manifests.append(json.loads(path.read_text(encoding="utf-8")))
        return {"run_mode": "DEVELOPMENT", "datasets": sorted(manifests, key=lambda m: m["uploaded_at"], reverse=True)}

    def evidence(self, dataset_id, **options):
        # 이벤트 분류·누락 기준에 따른 근거 생성
        options.pop("offset", None)
        options.pop("limit", None)
        first = self.read(dataset_id, offset=0, limit=1, **options)
        _, source_rows = parse_csv((self.directory / dataset_id / "source.csv").read_bytes())
        session_id = options.get("session_id")
        indexed = [(number, row) for number, row in enumerate(source_rows, start=1)
                   if session_id is None or row.get("session_id", "") == session_id]
        ids = Counter(row.get("event_id", "").strip() for _, row in indexed if row.get("event_id", "").strip())
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(first["rows"][0]))
        writer.writeheader()
        for row in preview_rows(indexed, ids, first["summary"]["target_selector_mapping"]):
            writer.writerow({key: ("'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
                             for key, value in row.items()})
        return output.getvalue().encode("utf-8-sig")
