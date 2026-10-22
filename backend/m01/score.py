# 수집 정확도 계산 및 근거 검산
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from fractions import Fraction

from ..evaluators import EvaluationError, require
from .upload import (
    EVENT_TYPES, LEGACY_MAPPING_VERSION, MAPPING_VERSION, REQUIRED_FIELDS,
    category, display, missing_fields,
)


V1_FORMAT = "m01-unified-evidence-v1"
FORMAT = "m01-unified-evidence-v2"
SUPPORTED_FORMATS = (V1_FORMAT, FORMAT)
FORMULA = "0.5*C1 + 0.3*(100-C2) + 0.2*C3"
TARGET = 65
MATCH_FIELDS = ("interaction_type", "page_url", "data_testid", "target_selector", "api_path", "api_method")
LEGACY_FIELDS = ("expected_event_id", "sequence", "expected_event_type", "expected_page_url",
                 "expected_data_testid", "expected_target_selector", "expected_api_path",
                 "expected_api_method", "matched_event_id", "matched_csv_row", "status", "reason")
V1_EVIDENCE_FIELDS = (("row_kind", "format_version", "metadata_key", "metadata_value") + LEGACY_FIELDS
                   + ("csv_row", "actual_event_id", "actual_event_id_sha256", "actual_session_id_sha256",
                      "raw_row_sha256", "raw_event_type", "raw_interaction_type", "ktl_type", "missing_fields",
                      "expected_event_id_sha256")
                   + tuple("required_" + key + "_sha256" for key in REQUIRED_FIELDS)
                   + tuple("expected_" + key + "_sha256" for key in MATCH_FIELDS)
                   + tuple("actual_" + key + "_sha256" for key in MATCH_FIELDS))
EVIDENCE_FIELDS = V1_EVIDENCE_FIELDS + ("raw_element_tag", "raw_input_control_type")
COUNT_KEYS = ("defined_required_event_count", "collected_required_event_count", "total_collected_events",
              "required_field_count", "missing_required_field_count", "defined_event_type_count",
              "collected_event_type_count")


def token(value):
    # 값 해시 비교 및 빈 조건 유지
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def measure(expected_count, matched_count, scoped_rows, session_id):
    require(expected_count > 0 and scoped_rows, "Expected and collected events are required for measurement")
    missing = Counter(key for _, row in scoped_rows for key in missing_fields(row))
    coverage = Counter(category(row) for _, row in scoped_rows)
    counts = {
        "defined_required_event_count": expected_count, "collected_required_event_count": matched_count,
        "total_collected_events": len(scoped_rows), "required_field_count": len(REQUIRED_FIELDS),
        "missing_required_field_count": sum(missing.values()), "defined_event_type_count": len(EVENT_TYPES),
        "collected_event_type_count": sum(bool(coverage[key]) for key in EVENT_TYPES),
    }
    c1 = matched_count / expected_count * 100
    c2 = counts["missing_required_field_count"] / (len(scoped_rows) * len(REQUIRED_FIELDS)) * 100
    c3 = counts["collected_event_type_count"] / len(EVENT_TYPES) * 100
    exact_weighted = (Fraction(50 * matched_count, expected_count)
                      + 30 - Fraction(30 * counts["missing_required_field_count"], len(scoped_rows) * len(REQUIRED_FIELDS))
                      + Fraction(20 * counts["collected_event_type_count"], len(EVENT_TYPES)))
    weighted = float(exact_weighted)
    return {"c1": c1, "c2": c2, "c3": c3, "collection_accuracy": weighted, "formula": FORMULA,
            "target": TARGET, "threshold_met": exact_weighted >= TARGET, "counts": counts,
            "field_policy": "RAW_REQUIRED_FIELDS", "required_fields": list(REQUIRED_FIELDS),
            "mapping_version": MAPPING_VERSION,
            "missing_fields": {key: missing[key] for key in REQUIRED_FIELDS},
            "type_counts": {key: coverage[key] for key in EVENT_TYPES},
            "missing_types": [key for key in EVENT_TYPES if not coverage[key]],
            "unclassified_event_count": coverage[None],
            "scope": {"session_id": session_id, "description": "whole CSV" if session_id is None else "selected session",
                      "all_original_rows_included": True},
            "notice": "DEVELOPMENT measurement; no official verdict. C2/C3 include every original row in the selected scope."}


def _safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "'")):
        return "'" + value
    return value


def _unescape(value):
    if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@", "'")):
        return value[1:]
    return value


def measurement_evidence(result, expected, comparison_rows, scoped_rows, actual_rows):
    # 입력값·화면 제목·요청 본문·세션 원문 제외
    published = {key: result["measurement"][key] for key in
                 ("c1", "c2", "c3", "collection_accuracy", "formula", "target", "threshold_met", "counts", "field_policy", "mapping_version")}
    metadata = {
        "comparison_id": result["comparison_id"], "dataset_id": result["dataset_id"], "truth_id": result["truth_id"],
        "scenario_name": display(result.get("scenario_name")), "scenario_version": display(result.get("scenario_version")),
        "collector_csv_sha256": result["input_sha256"]["collector_csv"],
        "expected_csv_sha256": result["input_sha256"]["expected_csv"],
        "scope_kind": "whole_csv" if result["session_id"] is None else "selected_session",
        "mapping_version": result["measurement"]["mapping_version"],
        "session_id_sha256": token(result["session_id"] or ""),
        "reported_measurement": json.dumps(published, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EVIDENCE_FIELDS)
    writer.writeheader()

    def write(row):
        writer.writerow({key: _safe_cell(value) for key, value in dict(row, format_version=FORMAT).items()})

    for key, value in metadata.items():
        write({"row_kind": "METADATA", "metadata_key": key, "metadata_value": value})
    for item, comparison in zip(expected, comparison_rows):
        row = dict(comparison, row_kind="EXPECTED", expected_event_id_sha256=token(item["expected_event_id"]))
        row.update({"expected_" + key + "_sha256": token(item[key]) for key in MATCH_FIELDS})
        write(row)
    actual_by_row = {item["csv_row"]: item for item in actual_rows}
    for number, raw in scoped_rows:
        item = actual_by_row[number]
        row = {"row_kind": "COLLECTED", "csv_row": number, "actual_event_id": display(item["event_id"]),
               "actual_event_id_sha256": token(item["event_id"]), "actual_session_id_sha256": token(raw.get("session_id", "")),
               "raw_row_sha256": token(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
               "raw_event_type": display(raw.get("event_type", "")).strip().lower(),
               "raw_interaction_type": display(raw.get("interaction_type", "")).strip().lower(),
               "raw_element_tag": display(raw.get("element_tag", "")).strip().lower(),
               "raw_input_control_type": display(raw.get("input_control_type", "")).strip().lower(),
               "ktl_type": item["event_type"] or "unclassified", "missing_fields": ",".join(missing_fields(raw))}
        row.update({"required_" + key + "_sha256": token(raw.get(key, "").strip()) for key in REQUIRED_FIELDS})
        row.update({"actual_" + key + "_sha256": token(item[key]) for key in MATCH_FIELDS})
        write(row)
    return output.getvalue().encode("utf-8-sig")


def _evidence_integer(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,8}", value), "Invalid evidence " + label)
    return int(value)


def _valid_token(value):
    return value == "" or bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _evidence_matches(expected, actual):
    if not actual["actual_event_id_sha256"] or expected["expected_event_type"] != actual["ktl_type"]:
        return False
    for key in ("interaction_type", "page_url", "api_path", "api_method"):
        condition = expected["expected_" + key + "_sha256"]
        if condition and condition != actual["actual_" + key + "_sha256"]:
            return False
    target = "data_testid" if expected["expected_data_testid_sha256"] else "target_selector"
    return not expected["expected_" + target + "_sha256"] or (
        expected["expected_" + target + "_sha256"] == actual["actual_" + target + "_sha256"])


def _maximum_matches(expected, actual):
    require(len(expected) * len(actual) <= 10000000, "Evidence comparison exceeds the supported size")
    previous = [0] * (len(actual) + 1)
    for item in expected:
        current = [0]
        for index, row in enumerate(actual, start=1):
            current.append(previous[index - 1] + 1 if _evidence_matches(item, row) else max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _same_measurement(calculated, reported):
    require(isinstance(reported, dict), "Evidence reported measurement is invalid")
    for key in ("c1", "c2", "c3", "collection_accuracy", "target"):
        value = reported.get(key)
        require(type(value) in (int, float) and math.isfinite(value)
                and math.isclose(calculated[key], value, rel_tol=0, abs_tol=1e-9), "Evidence recalculation differs: " + key)
    require(reported.get("formula") == FORMULA and reported.get("field_policy") == "RAW_REQUIRED_FIELDS",
            "Evidence measurement policy mismatch")
    require(type(reported.get("threshold_met")) is bool and reported["threshold_met"] == calculated["threshold_met"],
            "Evidence recalculation differs: threshold_met")
    require(isinstance(reported.get("counts"), dict) and all(type(reported["counts"].get(key)) is int
            and reported["counts"][key] == calculated["counts"][key] for key in COUNT_KEYS),
            "Evidence recalculation differs: counts")


def verify(raw, result=None):
    # 원본 데이터 없이 근거 CSV만으로 검산
    require(result is None or isinstance(result, dict), "Result must be a JSON object")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames == list(EVIDENCE_FIELDS):
            evidence_format = FORMAT
        elif reader.fieldnames == list(V1_EVIDENCE_FIELDS):
            evidence_format = V1_FORMAT
        else:
            if reader.fieldnames == list(LEGACY_FIELDS):
                return {"status": "LEGACY_UNAVAILABLE", "verified": None, "recalculated": None, "differences": [],
                        "notice": "Legacy evidence contains matches only; create a new comparison for weighted CSV verification."}
            raise EvaluationError("Unrecognized M01 evidence CSV schema")
        rows = []
        for row in reader:
            require(None not in row and all(value is not None for value in row.values()), "Malformed evidence row")
            rows.append({key: _unescape(value) for key, value in row.items()})
    except (UnicodeError, csv.Error):
        raise EvaluationError("Invalid UTF-8 M01 evidence CSV")
    require(rows and all(row["format_version"] == evidence_format and row["row_kind"] in {"METADATA", "EXPECTED", "COLLECTED"}
                         for row in rows), "Invalid evidence format or row kind")
    metadata = {}
    for row in rows:
        if row["row_kind"] == "METADATA":
            key = row["metadata_key"]
            require(key and key not in metadata, "Duplicate evidence metadata")
            metadata[key] = row["metadata_value"]
    metadata_keys = {"comparison_id", "dataset_id", "truth_id", "scenario_name", "scenario_version",
                     "collector_csv_sha256", "expected_csv_sha256", "scope_kind", "session_id_sha256", "reported_measurement"}
    if evidence_format == FORMAT:
        metadata_keys.add("mapping_version")
        require(metadata.get("mapping_version") == MAPPING_VERSION, "Evidence type mapping version mismatch")
    mapping_version = MAPPING_VERSION if evidence_format == FORMAT else LEGACY_MAPPING_VERSION
    require(set(metadata) == metadata_keys, "Evidence metadata is incomplete")
    require(all(re.fullmatch(r"[0-9a-f]{32}", metadata[key]) for key in ("comparison_id", "dataset_id", "truth_id")),
            "Invalid evidence provenance IDs")
    require(all(re.fullmatch(r"[0-9a-f]{64}", metadata[key]) for key in ("collector_csv_sha256", "expected_csv_sha256")),
            "Invalid evidence input hashes")
    require(metadata["scope_kind"] in {"whole_csv", "selected_session"} and _valid_token(metadata["session_id_sha256"]),
            "Invalid evidence collection scope")
    expected = [row for row in rows if row["row_kind"] == "EXPECTED"]
    collected = [row for row in rows if row["row_kind"] == "COLLECTED"]
    require(0 < len(expected) <= 1000 and 0 < len(collected) <= 100000, "Evidence requires expected and collected rows")
    token_keys = [key for key in EVIDENCE_FIELDS if key.endswith("_sha256")]
    require(all(_valid_token(row[key]) for row in expected + collected for key in token_keys), "Invalid evidence field hash")
    sequences = [_evidence_integer(row["sequence"], "sequence") for row in expected]
    require(sequences == sorted(set(sequences)), "Evidence expected sequence is not unique and ordered")
    require(len({row["expected_event_id_sha256"] for row in expected}) == len(expected)
            and all(row["expected_event_id_sha256"] and row["expected_event_type"] in EVENT_TYPES for row in expected),
            "Invalid evidence expected identity or type")
    for row in expected:
        kind = row["expected_event_type"]
        if kind in {"click", "input", "select_change", "submit_save", "key_input", "popup"}:
            require(row["expected_page_url_sha256"] and (row["expected_data_testid_sha256"] or row["expected_target_selector_sha256"]),
                    "Evidence DOM/popup conditions are incomplete")
        elif kind == "navigation":
            require(row["expected_page_url_sha256"], "Evidence navigation conditions are incomplete")
        elif kind == "network":
            require(row["expected_api_path_sha256"] and row["expected_api_method_sha256"], "Evidence API conditions are incomplete")
    numbers = [_evidence_integer(row["csv_row"], "CSV row") for row in collected]
    require(numbers == sorted(set(numbers)), "Evidence collected rows are not unique and ordered")
    by_number, unique, seen, missing, coverage = {}, [], {}, Counter(), Counter()
    for row in collected:
        require(row["raw_row_sha256"], "Evidence raw row hash is required")
        kind = category({"event_type": row["raw_event_type"], "interaction_type": row["raw_interaction_type"],
                         "element_tag": row.get("raw_element_tag", ""),
                         "input_control_type": row.get("raw_input_control_type", "")}, mapping_version=mapping_version)
        require(row["ktl_type"] == (kind or "unclassified"), "Evidence event category mismatch")
        coverage[kind] += 1
        missing_here = [key for key in REQUIRED_FIELDS if not row["required_" + key + "_sha256"]]
        require(row["missing_fields"] == ",".join(missing_here), "Evidence missing-field detail mismatch")
        missing.update(missing_here)
        if metadata["scope_kind"] == "selected_session":
            require(row["actual_session_id_sha256"] == metadata["session_id_sha256"], "Evidence row is outside selected session")
        by_number[row["csv_row"]] = row
        event_id = row["actual_event_id_sha256"]
        if event_id and event_id in seen:
            require(seen[event_id] == row["raw_row_sha256"], "Conflicting duplicate evidence event ID")
        else:
            if event_id:
                seen[event_id] = row["raw_row_sha256"]
            unique.append(row)
    matched, last, used = 0, 0, set()
    for row in expected:
        require(row["status"] in {"MATCHED", "MISSING"}, "Invalid evidence match status")
        if row["status"] == "MISSING":
            require(not row["matched_csv_row"] and not row["matched_event_id"], "Missing event has a claimed match")
            continue
        number = _evidence_integer(row["matched_csv_row"], "matched CSV row")
        event = by_number.get(str(number))
        require(event is not None and number > last and _evidence_matches(row, event), "Evidence match conditions or sequence mismatch")
        require(event["actual_event_id_sha256"] not in used and row["matched_event_id"] == event["actual_event_id"],
                "Evidence match reuses an event or mismatches identity")
        used.add(event["actual_event_id_sha256"])
        matched, last = matched + 1, number
    require(matched == _maximum_matches(expected, unique), "Evidence matches differ from independent maximum ordered matching")
    counts = {"defined_required_event_count": len(expected), "collected_required_event_count": matched,
              "total_collected_events": len(collected), "required_field_count": len(REQUIRED_FIELDS),
              "missing_required_field_count": sum(missing.values()), "defined_event_type_count": len(EVENT_TYPES),
              "collected_event_type_count": sum(bool(coverage[key]) for key in EVENT_TYPES)}
    c1 = Fraction(100 * matched, len(expected))
    c2 = Fraction(100 * sum(missing.values()), len(collected) * len(REQUIRED_FIELDS))
    c3 = Fraction(100 * counts["collected_event_type_count"], len(EVENT_TYPES))
    weighted = c1 / 2 + 3 * (100 - c2) / 10 + c3 / 5
    calculated = {"c1": float(c1), "c2": float(c2), "c3": float(c3), "collection_accuracy": float(weighted),
                  "formula": FORMULA, "target": TARGET, "threshold_met": weighted >= TARGET, "counts": counts,
                  "field_policy": "RAW_REQUIRED_FIELDS", "mapping_version": mapping_version}
    try:
        published = json.loads(metadata["reported_measurement"])
    except ValueError:
        raise EvaluationError("Evidence reported measurement is invalid JSON")
    _same_measurement(calculated, published)
    if evidence_format == FORMAT:
        require(published.get("mapping_version") == mapping_version, "Evidence reported type mapping version mismatch")
    if result is not None:
        _same_measurement(calculated, result.get("measurement"))
        if evidence_format == FORMAT:
            require(result["measurement"].get("mapping_version") == mapping_version, "Evidence result type mapping version mismatch")
        require(all(metadata[key] == result.get(key) for key in ("comparison_id", "dataset_id", "truth_id")),
                "Evidence result provenance mismatch")
        require(metadata["collector_csv_sha256"] == result.get("input_sha256", {}).get("collector_csv")
                and metadata["expected_csv_sha256"] == result.get("input_sha256", {}).get("expected_csv"),
                "Evidence result input hash mismatch")
        require(metadata["scope_kind"] == ("whole_csv" if result.get("session_id") is None else "selected_session")
                and metadata["session_id_sha256"] == token(result.get("session_id") or ""), "Evidence result scope mismatch")
        require(result.get("summary", {}).get("matched_count") == matched
                and result.get("summary", {}).get("expected_count") == len(expected), "Evidence result match counts mismatch")
    return {"status": "VERIFIED", "verified": True, "recalculated": calculated, "differences": [],
            "evidence_format": evidence_format, "evidence_sha256": hashlib.sha256(raw).hexdigest(),
            "notice": "Recalculated from exported expected/collected rows and field-presence hashes; original values remain private. DEVELOPMENT only."}
