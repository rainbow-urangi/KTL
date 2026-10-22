# 정답 시나리오 저장 및 이벤트 비교
import base64
import binascii
import csv
import hashlib
import io
import json
import re
import uuid
from array import array
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..evaluators import EvaluationError, require
from .upload import (
    EVENT_TYPES, MAX_CSV_BYTES, category, display, display_url, parse_csv,
)
from .score import FORMAT, SUPPORTED_FORMATS, measure, measurement_evidence, verify


COMPARISON_VERSION = "m01-event-comparison-dev-v3"
TRUTH_HEADERS = ("expected_event_id", "sequence", "event_type", "interaction_type",
                 "page_url", "data_testid", "target_selector", "api_path", "api_method")
MAX_TRUTH_EVENTS = 1000
MAX_COMPARISON_CELLS = 10000000
DOM_TYPES = {"click", "input", "select_change", "submit_save", "key_input"}


def _identifier(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value), "Invalid " + label)
    return value


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise EvaluationError("Stored comparison metadata is unavailable or invalid")
    require(isinstance(value, dict), "Stored comparison metadata must be a JSON object")
    return value


def _canonical_url(value):
    # 화면 경로 유지 및 쿼리·프래그먼트 제거
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc or parts.username or parts.password:
            return None
        # 포트·IPv6 주소 형식 검사
        parts.port
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    except ValueError:
        return None


def _canonical_api(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        parts = urlsplit(value)
        if parts.scheme:
            if _canonical_url(value) is None:
                return None
        elif not value.startswith("/") or value.startswith("//"):
            return None
        return parts.path or "/"
    except ValueError:
        return None


def _truth_csv(raw):
    headers, rows = parse_csv(raw)
    require(set(headers) == set(TRUTH_HEADERS), "Expected-event CSV requires exactly: " + ",".join(TRUTH_HEADERS))
    require(len(rows) <= MAX_TRUTH_EVENTS, "Expected-event CSV maximum is 1000 rows")
    ids, sequences, normalized = set(), set(), []
    for row in rows:
        item = {key: row[key].strip() for key in TRUTH_HEADERS}
        require(all(len(value) <= 1000 and not any(ord(c) < 32 for c in value) for value in item.values()),
                "Expected-event fields must be at most 1000 characters without control characters")
        require(item["expected_event_id"] and item["expected_event_id"] not in ids,
                "Expected-event IDs must be nonempty and unique")
        require(re.fullmatch(r"[1-9][0-9]{0,8}", item["sequence"]), "sequence must be a positive integer")
        item["sequence"] = int(item["sequence"])
        require(item["sequence"] not in sequences, "Expected-event sequence values must be unique")
        require(item["event_type"] in EVENT_TYPES, "Expected event_type must be a canonical M01 category")
        item["interaction_type"] = item["interaction_type"].lower()
        if item["page_url"]:
            item["page_url"] = _canonical_url(item["page_url"])
            require(item["page_url"], "Expected page_url must be an absolute HTTP(S) URL without credentials")
        if item["api_path"]:
            item["api_path"] = _canonical_api(item["api_path"])
            require(item["api_path"], "Expected api_path must be an HTTP(S) URL or absolute path")
        item["api_method"] = item["api_method"].upper()
        if item["api_method"]:
            require(re.fullmatch(r"[A-Z]{1,20}", item["api_method"]), "Invalid expected API method")
        kind = item["event_type"]
        if kind in DOM_TYPES or kind == "popup":
            require(item["data_testid"] or item["target_selector"], "DOM/popup expected events require data_testid or target_selector")
            require(item["page_url"], "DOM/popup expected events require page_url to disambiguate the target")
        elif kind == "network":
            require(item["api_path"] and item["api_method"], "Network expected events require api_path and api_method")
        elif kind == "navigation":
            require(item["page_url"], "Navigation expected events require page_url")
        ids.add(item["expected_event_id"])
        sequences.add(item["sequence"])
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["sequence"])


def _scenario_text(value, label, maximum):
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum
            and not any(ord(c) < 32 for c in value),
            label + " must be nonempty text without control characters")
    return value.strip()


def _structured_truth(payload):
    name = _scenario_text(payload["scenario_name"], "scenario_name", 120)
    version = _scenario_text(payload["scenario_version"], "scenario_version", 80)
    rows = payload["expected_events"]
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_TRUTH_EVENTS,
            "expected_events must contain 1 to 1000 expected events")
    for row in rows:
        require(isinstance(row, dict) and set(row) == set(TRUTH_HEADERS),
                "Each expected event requires exactly: " + ",".join(TRUTH_HEADERS))
        require(all(isinstance(value, str) or (key == "sequence" and type(value) is int)
                    for key, value in row.items()), "Expected-event values must be strings; sequence may be an integer")
        require(all(len(str(value)) <= 1000 for value in row.values()),
                "Expected-event fields must be at most 1000 characters")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRUTH_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    expected = _truth_csv(output.getvalue().encode("utf-8-sig"))
    # 정답 저장 형식 통일
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRUTH_HEADERS)
    writer.writeheader()
    writer.writerows(expected)
    return name, version, expected, output.getvalue().encode("utf-8-sig")


def _truth_metadata(manifest):
    if manifest.get("source") == "stored_scenario":
        name = _scenario_text(manifest.get("scenario_name"), "Stored scenario_name", 120)
        version = _scenario_text(manifest.get("scenario_version"), "Stored scenario_version", 80)
        require(name == manifest.get("scenario_name") and version == manifest.get("scenario_version"),
                "Stored scenario metadata mismatch")
        return dict(manifest, legacy_csv=False)
    require(manifest.get("source") in (None, "csv_upload"), "Stored expected-event source is invalid")
    return dict(manifest, scenario_name=manifest.get("filename", "Previous CSV truth"),
                scenario_version="legacy", source="csv_upload", legacy_csv=True)


def _actual(row, csv_row):
    return {
        "event_id": row.get("event_id", "").strip(), "session_id": row.get("session_id", ""),
        "csv_row": csv_row, "event_type": category(row),
        "interaction_type": row.get("interaction_type", "").strip().lower(),
        "page_url": _canonical_url(row.get("page_url")),
        "data_testid": row.get("data_testid", "").strip(),
        "target_selector": row.get("target_selector", "").strip(),
        "api_path": _canonical_api(row.get("api_path")),
        "api_method": row.get("api_method", "").strip().upper(),
    }


def _matches(expected, actual):
    if not actual["event_id"] or expected["event_type"] != actual["event_type"]:
        return False
    for key in ("interaction_type", "page_url", "api_path", "api_method"):
        if expected[key] and expected[key] != actual[key]:
            return False
    # data_testid 우선 비교
    target = "data_testid" if expected["data_testid"] else "target_selector"
    if expected[target] and expected[target] != actual[target]:
        return False
    return True


def _ordered_pairs(expected, actual):
    # 순서를 유지하는 일대일 최대 매칭
    require(len(expected) * len(actual) <= MAX_COMPARISON_CELLS,
            "Comparison is too large; select a collection session or split the CSV (maximum 10000000 comparison cells)")
    table = [array("H", [0]) * (len(actual) + 1)]
    for item in expected:
        previous = table[-1]
        current = array("H", [0]) * (len(actual) + 1)
        for j, event in enumerate(actual, start=1):
            if _matches(item, event):
                current[j] = previous[j - 1] + 1
            else:
                current[j] = max(previous[j], current[j - 1])
        table.append(current)
    pairs, i, j = {}, len(expected), len(actual)
    while i and j:
        if _matches(expected[i - 1], actual[j - 1]) and table[i][j] == table[i - 1][j - 1] + 1:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return pairs


class M01ComparisonStore:
    def __init__(self, root):
        self.root = Path(root)
        self.truth_directory = self.root / "data/development/m01_ground_truth"
        self.directory = self.root / "data/development/m01_comparisons"

    def upload_truth(self, payload):
        require(isinstance(payload, dict), "Expected-event registration must be a JSON object")
        if set(payload) == {"scenario_name", "scenario_version", "expected_events"}:
            return self.register_scenario(payload)
        require(set(payload) == {"filename", "csv_base64"},
                "Expected-event registration requires scenario_name, scenario_version and expected_events, or filename and csv_base64")
        filename, encoded = payload["filename"], payload["csv_base64"]
        require(isinstance(filename, str) and 0 < len(filename) <= 255 and filename.lower().endswith(".csv")
                and "/" not in filename and "\\" not in filename and not any(ord(c) < 32 for c in filename),
                "A CSV filename without a path is required")
        require(isinstance(encoded, str) and len(encoded) <= ((MAX_CSV_BYTES + 2) // 3) * 4,
                "Expected-event CSV base64 required; maximum file size 10 MiB")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise EvaluationError("Invalid expected-event CSV base64")
        expected = _truth_csv(raw)
        return self._save_truth(raw, expected, display(filename), {"source": "csv_upload"})

    def register_scenario(self, payload):
        name, version, expected, raw = _structured_truth(payload)
        for truth in self.list_truths()["truths"]:
            if not truth["legacy_csv"] and (truth["scenario_name"], truth["scenario_version"]) == (name, version):
                require(truth["sha256"] == _digest(raw),
                        "This scenario version is already fixed with different expected events; register a new scenario_version")
                return self.read_truth(truth["truth_id"])
        return self._save_truth(raw, expected, "expected_events.csv",
                                {"source": "stored_scenario", "scenario_name": name, "scenario_version": version})

    def _save_truth(self, raw, expected, filename, metadata):
        truth_id = uuid.uuid4().hex
        truth = {"truth_id": truth_id, "filename": filename, "sha256": _digest(raw),
                 "event_count": len(expected), "uploaded_at": datetime.now(timezone.utc).isoformat(),
                 "run_mode": "DEVELOPMENT", "evaluator_version": COMPARISON_VERSION, **metadata}
        directory = self.truth_directory / truth_id
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "source.csv").write_bytes(raw)
        _json(directory / "manifest.json", truth)
        return {"truth": _truth_metadata(truth), "expected": expected, "run_mode": "DEVELOPMENT"}

    def _truth(self, truth_id):
        directory = self.truth_directory / _identifier(truth_id, "truth ID")
        if not (directory / "manifest.json").is_file():
            raise EvaluationError("Expected-event dataset not found", "NOT_FOUND")
        manifest = _read_json(directory / "manifest.json")
        try:
            raw = (directory / "source.csv").read_bytes()
        except OSError:
            raise EvaluationError("Stored expected-event CSV is unavailable")
        require(manifest.get("truth_id") == truth_id and manifest.get("run_mode") == "DEVELOPMENT",
                "Stored expected-event metadata mismatch")
        require(_digest(raw) == manifest.get("sha256"), "Stored expected-event CSV hash mismatch")
        expected = _truth_csv(raw)
        require(len(expected) == manifest.get("event_count"), "Stored expected-event count mismatch")
        return _truth_metadata(manifest), expected, raw

    def read_truth(self, truth_id):
        truth, expected, _ = self._truth(truth_id)
        return {"truth": truth, "expected": expected, "run_mode": "DEVELOPMENT"}

    def list_truths(self):
        truths = []
        if self.truth_directory.exists():
            for path in self.truth_directory.glob("*/manifest.json"):
                if re.fullmatch(r"[0-9a-f]{32}", path.parent.name):
                    manifest, _, _ = self._truth(path.parent.name)
                    truths.append(manifest)
        return {"truths": sorted(truths, key=lambda item: item["uploaded_at"], reverse=True), "run_mode": "DEVELOPMENT"}

    def compare(self, payload, config):
        require(isinstance(payload, dict) and {"dataset_id", "truth_id"} <= set(payload)
                and set(payload) <= {"dataset_id", "truth_id", "session_id"},
                "Comparison requires dataset_id, truth_id and optional session_id")
        dataset_id = _identifier(payload["dataset_id"], "dataset ID")
        truth_id = _identifier(payload["truth_id"], "truth ID")
        session_id = payload.get("session_id")
        require(session_id is None or (isinstance(session_id, str) and len(session_id) <= 1000
                and not any(ord(c) < 32 for c in session_id)), "session_id must be a string")
        source_directory = self.root / "data/development/m01_uploads" / dataset_id
        if not (source_directory / "manifest.json").is_file():
            raise EvaluationError("CSV dataset not found", "NOT_FOUND")
        source_manifest = _read_json(source_directory / "manifest.json")
        try:
            source_raw = (source_directory / "source.csv").read_bytes()
        except OSError:
            raise EvaluationError("Stored collector CSV is unavailable")
        require(source_manifest.get("dataset_id") == dataset_id and source_manifest.get("run_mode") == "DEVELOPMENT",
                "Stored collector metadata mismatch")
        require(_digest(source_raw) == source_manifest.get("sha256"), "Stored CSV hash mismatch")
        _, source_rows = parse_csv(source_raw)
        truth, expected, truth_raw = self._truth(truth_id)
        # 세션 선택 전 전체 이벤트 ID 중복 충돌 검사
        seen = {}
        for row in source_rows:
            event_id = row.get("event_id", "").strip()
            if event_id in seen and event_id:
                require(seen[event_id] == row, "Conflicting rows share an event_id; comparison aborted")
            elif event_id:
                seen[event_id] = row
        scoped_rows = [(number, row) for number, row in enumerate(source_rows, start=2)
                       if session_id is None or row.get("session_id", "") == session_id]
        actual, selected_ids, duplicate_rows = [], set(), 0
        for number, row in scoped_rows:
            event_id = row.get("event_id", "").strip()
            if event_id and event_id in selected_ids:
                duplicate_rows += 1
                continue
            if event_id:
                selected_ids.add(event_id)
            actual.append(_actual(row, number))
        require(actual, "No events in the selected collection scope")
        pairs = _ordered_pairs(expected, actual)
        rows = []
        for i, item in enumerate(expected):
            event = actual[pairs[i]] if i in pairs else None
            rows.append({
                "expected_event_id": display(item["expected_event_id"]), "sequence": item["sequence"],
                "expected_event_type": item["event_type"], "expected_page_url": display_url(item["page_url"]),
                "expected_data_testid": display(item["data_testid"]), "expected_target_selector": display(item["target_selector"]),
                "expected_api_path": display(item["api_path"]), "expected_api_method": item["api_method"],
                "matched_event_id": display(event["event_id"]) if event else None,
                "matched_csv_row": event["csv_row"] if event else None,
                "status": "MATCHED" if event else "MISSING",
                "reason": "Type, required conditions and sequence matched" if event else "No unused event matched all required conditions in order",
            })
        matched = len(pairs)
        comparison_id = uuid.uuid4().hex
        result = {
            "comparison_id": comparison_id, "dataset_id": dataset_id, "truth_id": truth_id,
            "scenario_name": truth["scenario_name"], "scenario_version": truth["scenario_version"],
            "run_mode": "DEVELOPMENT", "status": "DEVELOPMENT_EVENT_COMPARISON", "evaluator_version": COMPARISON_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
            "summary": {"expected_count": len(expected), "matched_count": matched,
                        "missing_count": len(expected) - matched, "extra_event_count": len(actual) - matched,
                        "duplicate_event_rows": duplicate_rows, "source_event_count": len(source_rows),
                        "scoped_unique_event_count": len(actual), "match_rate": matched / len(expected) * 100,
                        "score": None, "official_pass": None},
            "score": None, "official_pass": None, "rows": rows,
            "measurement": measure(len(expected), matched, scoped_rows, session_id),
            "input_sha256": {"collector_csv": _digest(source_raw), "expected_csv": _digest(truth_raw)},
            "evidence_file": "/api/development/m01/comparisons/" + comparison_id + "/evidence.csv",
            "verification_file": "/api/development/m01/comparisons/" + comparison_id + "/verification",
            "notice": "Development weighted M01 measurement and expected-event match rate; no official verdict. Input values and API bodies are not compared.",
        }
        directory = self.directory / comparison_id
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "truth.csv").write_bytes(truth_raw)
        _json(directory / "truth_snapshot.json", {"truth": truth, "expected": expected})
        _json(directory / "result.json", result)
        evidence = measurement_evidence(result, expected, rows, scoped_rows,
                                        [_actual(row, number) for number, row in scoped_rows])
        (directory / "evidence.csv").write_bytes(evidence)
        verification = verify((directory / "evidence.csv").read_bytes(), _read_json(directory / "result.json"))
        _json(directory / "verification.json", verification)
        _json(directory / "manifest.json", {"comparison_id": comparison_id, "run_mode": "DEVELOPMENT",
              "input_sha256": result["input_sha256"], "result_sha256": _digest((directory / "result.json").read_bytes()),
              "evidence_sha256": _digest(evidence), "truth_snapshot_sha256": _digest((directory / "truth_snapshot.json").read_bytes()),
              "evidence_format": FORMAT, "verification_sha256": _digest((directory / "verification.json").read_bytes())})
        return result

    def read(self, comparison_id):
        directory = self.directory / _identifier(comparison_id, "comparison ID")
        if not (directory / "manifest.json").is_file():
            raise EvaluationError("Comparison not found", "NOT_FOUND")
        manifest = _read_json(directory / "manifest.json")
        require(manifest.get("comparison_id") == comparison_id and manifest.get("run_mode") == "DEVELOPMENT",
                "Stored comparison metadata mismatch")
        try:
            raw = (directory / "result.json").read_bytes()
            truth_raw = (directory / "truth.csv").read_bytes()
            snapshot_raw = (directory / "truth_snapshot.json").read_bytes()
            evidence_raw = (directory / "evidence.csv").read_bytes()
        except OSError:
            raise EvaluationError("Stored comparison evidence is unavailable")
        require(_digest(raw) == manifest.get("result_sha256")
                and _digest(truth_raw) == manifest.get("input_sha256", {}).get("expected_csv")
                and _digest(snapshot_raw) == manifest.get("truth_snapshot_sha256")
                and _digest(evidence_raw) == manifest.get("evidence_sha256"), "Stored comparison evidence hash mismatch")
        if manifest.get("evidence_format") in SUPPORTED_FORMATS:
            try:
                verification_raw = (directory / "verification.json").read_bytes()
            except OSError:
                raise EvaluationError("Stored comparison verification is unavailable")
            require(_digest(verification_raw) == manifest.get("verification_sha256"), "Stored comparison verification hash mismatch")
        result = _read_json(directory / "result.json")
        require(result.get("comparison_id") == comparison_id and result.get("run_mode") == "DEVELOPMENT",
                "Stored comparison result mismatch")
        return result

    def evidence(self, comparison_id):
        self.read(comparison_id)
        return (self.directory / comparison_id / "evidence.csv").read_bytes()

    def verification(self, comparison_id):
        result = self.read(comparison_id)
        return verify((self.directory / comparison_id / "evidence.csv").read_bytes(), result)
