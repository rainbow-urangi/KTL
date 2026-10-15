"""Validate new CSV inputs without fitting features, changing vocabularies or inference."""
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

CATEGORIES = ("event_type", "interaction_type", "element_tag", "api_method")
EVENT_REQUIRED = ("event_id", "session_id", "event_time", *CATEGORIES, "element_text", "associated_label", "api_path")
EVENT_OPTIONAL = ("id", "page_title", "page_url", "data_testid", "step_duration_ms", "api_latency_ms", "api_status_code",
                  "input_data", "actor_key", "login_id", "user_id", "worker_id", "employee_id", "workflow_key",
                  "task_id", "workflow_index", "workflow_outcome", "target_selector", "locators_json", "selector_xpath")
NULL_TOKENS = {"", "nan", "none", "null", "nat", "[null]"}


def clean(value):
    value = str(value).strip() if value is not None else ""
    return "" if value.lower() in NULL_TOKENS else value


def validate_csvs(events_path, sessions_path, vocabularies, tasks_path=None):
    errors, warnings, counts = [], [], {}
    def issue(target, code, **details):
        target.append({"code": code, **details})

    def read(path, label):
        try:
            with Path(path).open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames or []
                if len(columns) != len(set(columns)):
                    issue(errors, "duplicate_columns", file=label)
                rows = list(reader)
                if any(None in row or any(v is None for v in row.values()) for row in rows):
                    issue(errors, "malformed_csv_row", file=label)
                counts[label] = len(rows)
                return columns, rows
        except (OSError, UnicodeError, csv.Error, TypeError) as exc:
            issue(errors, "csv_read_error", file=label, message=str(exc))
            return [], []

    for name in CATEGORIES:
        mapping = vocabularies.get(name, {})
        if mapping.get("<PAD>") != 0 or mapping.get("<UNK>") != 1:
            raise ValueError(f"검증된 frozen vocabulary가 필요합니다: {name}")
    ec, events = read(events_path, "events")
    sc, sessions = read(sessions_path, "sessions")
    for name in EVENT_REQUIRED:
        if name not in ec:
            issue(errors, "missing_column", file="events", column=name)
    key = "session_id" if "session_id" in sc else "id" if "id" in sc else None
    if key is None:
        issue(errors, "missing_session_key", file="sessions")
    if "user_id" not in sc:
        issue(errors, "missing_column", file="sessions", column="user_id")
    if not events:
        issue(errors, "empty_events")

    session_users = defaultdict(set)
    for index, row in enumerate(sessions, 2):
        sid, user = clean(row.get(key)), clean(row.get("user_id"))
        if not sid or not user:
            issue(errors, "null_session_identity", row=index)
        if sid:
            session_users[sid].add(user)
    for sid, users in session_users.items():
        if len(users) > 1:
            # Do not include raw user identifiers in the diagnostic output.
            issue(errors, "conflicting_session_user", session_id=sid)
    if key:
        duplicate_sessions = sum(n - 1 for n in Counter(clean(r.get(key)) for r in sessions).values() if n > 1)
        if duplicate_sessions:
            issue(warnings, "duplicate_session_rows", count=duplicate_sessions)

    seen = set()
    oov = {name: {"count": 0, "null_count": 0, "non_null_count": 0, "rate": 0.0, "denominator": "non-null values"} for name in CATEGORIES}
    timestamp_modes = set()
    for index, row in enumerate(events, 2):
        event_id, sid = clean(row.get("event_id")), clean(row.get("session_id"))
        if not event_id:
            issue(errors, "null_event_id", row=index)
        elif event_id in seen:
            issue(errors, "duplicate_event_id", row=index, event_id=event_id)
        seen.add(event_id)
        if not sid:
            issue(errors, "null_event_session", row=index)
        elif sid not in session_users:
            issue(errors, "unknown_session_reference", row=index, session_id=sid)
        raw_time = clean(row.get("event_time"))
        try:
            stamp = pd.to_datetime(raw_time, errors="raise") if raw_time else pd.NaT
            if pd.isna(stamp):
                raise ValueError("missing timestamp")
            timestamp_modes.add("aware" if stamp.tzinfo else "naive")
        except (ValueError, TypeError, OverflowError):
            issue(errors, "invalid_event_timestamp", row=index)
        for name in CATEGORIES:
            value = clean(row.get(name))
            if not value:
                oov[name]["null_count"] += 1
            else:
                oov[name]["non_null_count"] += 1
                # Reserved tokens in incoming data are not valid learned categories.
                if value not in vocabularies[name] or value in {"<PAD>", "<UNK>"}:
                    oov[name]["count"] += 1
        for name in ("step_duration_ms", "api_latency_ms", "api_status_code"):
            value = clean(row.get(name))
            if not value:
                continue
            try:
                number = float(pd.to_numeric(value, errors="raise"))
                if not math.isfinite(number):
                    raise ValueError("non-finite")
                if number < 0:
                    issue(errors, "negative_numeric_value", row=index, column=name)
            except (ValueError, OverflowError):
                issue(errors, "numeric_parse_error", row=index, column=name)
    if len(timestamp_modes) > 1:
        issue(errors, "mixed_timestamp_awareness")
    for name, report in oov.items():
        report["rate"] = report["count"] / report["non_null_count"] if report["non_null_count"] else 0.0
        if report["count"]:
            issue(warnings, "categorical_oov", column=name, count=report["count"], rate=report["rate"], future_action="UNK")
    if "user_id" in ec:
        issue(warnings, "event_user_id_policy_unresolved", message="user_id는 상위 trajectory 전용입니다. low-level stream 정책은 미확정입니다.")
    for label, rows in [("sessions", sessions)]:
        for index, row in enumerate(rows, 2):
            for field in ("start_time", "end_time"):
                value = clean(row.get(field))
                if value:
                    try:
                        if pd.isna(pd.to_datetime(value, errors="raise")):
                            raise ValueError("invalid")
                    except (ValueError, TypeError, OverflowError):
                        issue(errors, "invalid_optional_timestamp", file=label, row=index, column=field)
    if tasks_path is not None:
        _, tasks = read(tasks_path, "tasks")
        issue(warnings, "tasks_not_used_by_model", count=len(tasks))
    return {"valid": not errors, "errors": errors, "warnings": warnings, "row_counts": counts,
            "categorical_oov": oov, "unknown_columns": sorted(set(ec) - set(EVENT_REQUIRED) - set(EVENT_OPTIONAL)),
            "inference_executed": False, "vocabulary_modified": False}
