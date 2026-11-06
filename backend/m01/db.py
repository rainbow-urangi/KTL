# PROD DB 읽기 전용 조회
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


MAX_LIMIT = 100
MAX_PAGE = 100000
MAX_RANGE_DAYS = 90
QUERY_TIMEOUT_SECONDS = 5
FIELDS = ("id", "event_id", "session_id", "event_time", "event_type", "interaction_type",
          "page_url", "page_title", "target_selector", "api_path", "api_method", "api_status_code")
REQUIRED_COLUMNS = frozenset(("id", "event_id", "session_id", "event_time", "event_type",
                              "interaction_type", "page_url", "target_selector"))
ENV_NAMES = tuple("KTL_PROD_DB_" + key for key in
                  ("HOST", "PORT", "USER", "PASSWORD", "DATABASE", "TIME_OFFSET"))
POLICY = {"max_range_days": MAX_RANGE_DAYS, "max_page_size": MAX_LIMIT,
          "max_page": MAX_PAGE, "dates_optional": True}


class M01ProdError(Exception):
    # 외부 공개용 오류 코드·메시지
    def __init__(self, code, message, http_status=503):
        super().__init__(code)
        self.code = code
        self.message = message
        self.http_status = http_status


def _invalid(message):
    raise M01ProdError("m01_prod_invalid_query", message, 400)


def _local_environment(root):
    path = Path(root) / ".env.local"
    result = {}
    if not path.is_file():
        return result
    try:
        if path.stat().st_size > 32768:
            raise ValueError("oversize")
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            key = key.strip()
            if separator and key in ENV_NAMES:
                value = value.strip()
                if value.startswith('"'):
                    value = json.loads(value)
                    if not isinstance(value, str):
                        raise ValueError("string required")
                elif len(value) >= 2 and value[0] == value[-1] == "'":
                    value = value[1:-1]
                result[key] = value
    except (OSError, UnicodeError, ValueError):
        raise M01ProdError("m01_prod_config_invalid", "로컬 PROD 조회 설정 파일을 읽을 수 없습니다.") from None
    return result


def _configuration(root):
    values = _local_environment(root)
    values.update({name: os.environ[name] for name in ENV_NAMES if name in os.environ})
    result = {name: values.get("KTL_PROD_DB_" + name, "") for name in
              ("HOST", "USER", "PASSWORD", "DATABASE")}
    result["HOST"] = result["HOST"].strip()
    result["USER"] = result["USER"].strip()
    result["DATABASE"] = result["DATABASE"].strip()
    result["TIME_OFFSET"] = values.get("KTL_PROD_DB_TIME_OFFSET", "+09:00").strip()
    try:
        result["PORT"] = int(values.get("KTL_PROD_DB_PORT", "3306"))
    except (ValueError, TypeError):
        result["PORT"] = 0
    if not all(result[name] for name in ("HOST", "USER", "PASSWORD", "DATABASE")):
        raise M01ProdError("m01_prod_config_required", "PROD 수집 DB 전용 읽기 연결 설정이 필요합니다.")
    if (not re.fullmatch(r"[A-Za-z0-9_]{1,64}", result["DATABASE"])
            or not 1 <= result["PORT"] <= 65535
            or result["TIME_OFFSET"] not in {"+09:00", "+00:00"}
            or len(result["HOST"]) > 253 or len(result["USER"]) > 128
            or len(result["PASSWORD"]) > 4096
            or any(re.search(r"[\x00-\x1f\x7f]", result[name]) for name in ("HOST", "USER", "PASSWORD"))):
        raise M01ProdError("m01_prod_config_invalid", "PROD 조회 연결 설정 형식을 확인해 주세요.")
    return result


def _load_driver():
    try:
        import pymysql
        return pymysql
    except ImportError:
        return None


def get_status(root):
    status = {"configured": False, "read_only": True, "connection_status": "not_checked",
              "driver_available": _load_driver() is not None, "event_time_offset": None,
              "policy": dict(POLICY), "official": False}
    try:
        config = _configuration(root)
        status.update(configured=True, event_time_offset=config["TIME_OFFSET"])
    except M01ProdError as error:
        status.update(code=error.code, message=error.message)
    if status["configured"] and not status["driver_available"]:
        status.update(code="m01_prod_driver_required", message="PROD 조회에는 PyMySQL 설치가 필요합니다.")
    return status


def _text(value, name, maximum):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > maximum or re.search(r"[\x00-\x1f\x7f]", value):
        _invalid(name + " 값의 형식 또는 길이를 확인해 주세요.")
    return value.strip() or None


def _integer(value, name, default, maximum):
    if value is None or value == "":
        return default
    if type(value) not in (str, int) or not re.fullmatch(r"[0-9]{1,9}", str(value)):
        _invalid(name + " 값은 양의 정수여야 합니다.")
    number = int(value)
    if not 1 <= number <= maximum:
        _invalid(name + " 값이 허용 범위를 벗어났습니다.")
    return number


def _zone(offset):
    return timezone(timedelta(hours=9) if offset == "+09:00" else timedelta(0))


def _date_bound(value, name, stored_zone):
    text = _text(value, name, 40)
    if text is None:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = date.fromisoformat(text)
            return datetime.combine(day, time.min if name == "from" else time.max, stored_zone)
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("timezone required")
        return stamp.astimezone(stored_zone)
    except (ValueError, OverflowError):
        _invalid(name + " 값은 날짜 또는 시간대가 있는 ISO 시각이어야 합니다.")


def _filters(query, offset):
    if not isinstance(query, dict) or set(query) - {"from", "to", "session_id", "event_id", "page", "limit"}:
        _invalid("허용되지 않은 조회 조건이 있습니다.")
    start = _date_bound(query.get("from"), "from", _zone(offset))
    end = _date_bound(query.get("to"), "to", _zone(offset))
    if start is not None and end is not None and (end < start or end - start > timedelta(days=MAX_RANGE_DAYS)):
        _invalid("시작·종료일을 모두 지정한 조회 기간은 0~90일이어야 합니다.")
    return {"from": start, "to": end, "session_id": _text(query.get("session_id"), "session_id", 128),
            "event_id": _text(query.get("event_id"), "event_id", 128),
            "page": _integer(query.get("page"), "page", 1, MAX_PAGE),
            "limit": _integer(query.get("limit"), "limit", 50, MAX_LIMIT)}


def _mask_text(value, maximum=500):
    if value is None:
        return None
    text = str(value)[:maximum]
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    text = re.sub(r"(?<![A-Za-z0-9])(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?![A-Za-z0-9])",
                  "[REDACTED_PHONE]", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [REDACTED]", text)
    return re.sub(r"(?i)(password|passwd|pwd|token|authorization|cookie|secret|api[_-]?key)(\s*[=:]\s*)"
                  r"(?:['\"][^'\"]*['\"]|[^\s,;\]}]+)", r"\1\2[REDACTED]", text)


def _safe_url(value):
    if value is None:
        return None
    try:
        parts = urlsplit(str(value)[:4096])
        if parts.scheme and parts.scheme.lower() not in {"http", "https"}:
            return "[REDACTED_URL]"
        host = parts.netloc.rsplit("@", 1)[-1]
        path = re.sub(r"(?i)(/(?:token|password|secret|api[_-]?key)/)[^/]+", r"\1[REDACTED]", parts.path)
        return _mask_text(urlunsplit((parts.scheme, host, path, "", "")), 2048)
    except (ValueError, TypeError):
        return "[INVALID_URL]"


def _safe_selector(value):
    if value is None:
        return None
    text = str(value)[:2048]
    if text.count("[") != text.count("]"):
        return "[REDACTED_SELECTOR]"
    def attribute(match):
        name = re.match(r"\[\s*@?([\w:-]+)", match.group(0))
        return match.group(0) if name and name.group(1).lower() in {
            "id", "class", "name", "type", "role", "data-testid"} else "[REDACTED_ATTRIBUTE]"
    return _mask_text(re.sub(r"\[[^\]]*\]", attribute, text), 2048)


def _timestamp(value, offset):
    if value is None:
        return None
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=_zone(offset))
        precision = "milliseconds" if stamp.microsecond % 1000 == 0 else "microseconds"
        return stamp.isoformat(timespec=precision)
    except (ValueError, TypeError, OverflowError):
        return None


def _safe_row(row, offset):
    result = {name: _mask_text(row.get(name)) for name in FIELDS}
    result["event_time"] = _timestamp(row.get("event_time"), offset)
    result["page_url"] = _safe_url(row.get("page_url"))
    result["api_path"] = _safe_url(row.get("api_path"))
    result["target_selector"] = _safe_selector(row.get("target_selector"))
    status = row.get("api_status_code")
    result["api_status_code"] = status if type(status) is int and 0 <= status <= 999 else None
    return result


def _database_failure(error):
    code = error.args[0] if error.args and type(error.args[0]) is int else None
    if code in {1044, 1045, 1142, 1227}:
        return M01ProdError("m01_prod_access_denied", "수집 DB 읽기 계정과 권한을 확인해 주세요.")
    if code in {1205, 1317, 1969} or isinstance(error, TimeoutError):
        return M01ProdError("m01_prod_query_timeout", "수집 DB 조회 시간이 초과되었습니다. 기간이나 세션을 좁혀 주세요.")
    if code in {1054, 1146}:
        return M01ProdError("m01_prod_schema_incompatible", "수집 DB 이벤트 스키마가 조회 계약과 다릅니다.")
    return M01ProdError("m01_prod_unavailable", "수집 DB에 연결하거나 조회할 수 없습니다. 연결 상태를 확인해 주세요.")


def query_events(root, querydict):
    config = _configuration(root)
    filters = _filters(querydict, config["TIME_OFFSET"])
    driver = _load_driver()
    if driver is None:
        raise M01ProdError("m01_prod_driver_required", "PROD 조회에는 PyMySQL 설치가 필요합니다.")
    connection = None
    try:
        connection = driver.connect(host=config["HOST"], port=config["PORT"], user=config["USER"],
                                    password=config["PASSWORD"], database=config["DATABASE"], charset="utf8mb4",
                                    connect_timeout=QUERY_TIMEOUT_SECONDS, read_timeout=QUERY_TIMEOUT_SECONDS,
                                    write_timeout=QUERY_TIMEOUT_SECONDS, autocommit=False,
                                    cursorclass=driver.cursors.DictCursor)
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SET STATEMENT max_statement_time=5 FOR SELECT COLUMN_NAME "
                           "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", ("events",))
            columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            if not REQUIRED_COLUMNS <= columns:
                raise M01ProdError("m01_prod_schema_incompatible", "수집 DB 이벤트 스키마가 조회 계약과 다릅니다.")
            where, parameters = [], []
            for name, operator in (("from", ">="), ("to", "<=")):
                if filters[name] is not None:
                    where.append("e.event_time " + operator + " %s")
                    parameters.append(filters[name].replace(tzinfo=None))
            for name in ("session_id", "event_id"):
                if filters[name] is not None:
                    where.append("e." + name + " = %s")
                    parameters.append(filters[name])
            projection = []
            for name in FIELDS:
                if name not in columns:
                    projection.append("NULL AS " + name)
                elif name in {"event_time", "api_status_code"}:
                    projection.append("e." + name)
                else:
                    maximum = 4096 if name in {"page_url", "api_path", "target_selector"} else 500
                    projection.append("LEFT(CAST(e." + name + " AS CHAR), " + str(maximum) + ") AS " + name)
            sql = "SET STATEMENT max_statement_time=5 FOR SELECT " + ", ".join(projection) + " FROM events e"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY e.event_time DESC, e.id DESC LIMIT %s OFFSET %s"
            parameters.extend((filters["limit"] + 1, (filters["page"] - 1) * filters["limit"]))
            cursor.execute(sql, tuple(parameters))
            rows = cursor.fetchall()
        source = {"kind": "PROD_DB", "read_only": True, "official": False, "connection_status": "connected",
                  "time_basis": "stored_datetime", "event_time_offset": config["TIME_OFFSET"],
                  "missing_columns": [name for name in FIELDS if name not in columns]}
        return {"source": source, "rows": [_safe_row(row, config["TIME_OFFSET"]) for row in rows[:filters["limit"]]],
                "page": filters["page"], "limit": filters["limit"], "has_more": len(rows) > filters["limit"],
                "total": None, "filters": {name: value.isoformat() if isinstance(value, datetime) else _mask_text(value)
                                            for name, value in filters.items() if name not in {"page", "limit"}},
                "notice": "운영 DB의 기존 이벤트를 읽기 전용으로 조회했습니다. 페이지 조회는 전체 M01 평가 점수가 아닙니다."}
    except M01ProdError:
        raise
    except Exception as error:
        raise _database_failure(error) from None
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass
