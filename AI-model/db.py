# ml/db.py
from __future__ import annotations

import pymysql
from pymysql.cursors import DictCursor

from config import DBConfig


def get_conn(cfg: DBConfig):
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        charset=cfg.charset,
        cursorclass=DictCursor,
        autocommit=True,
    )


def fetch_candidate_case_ids(
    db_cfg: DBConfig,
    rule_version: str,
    min_seq_len_clean: int,
    limit: int | None = None,
) -> list[int]:
    """
    case_sequences 기준으로 학습 가능한 case_id를 가져온다.
    기존 ETL 산출물을 그대로 사용한다.
    """
    sql = """
        SELECT case_id
        FROM case_sequences
        WHERE activity_rule_version = %s
          AND seq_len_clean >= %s
          AND seq_text_clean IS NOT NULL
          AND seq_text_clean <> ''
        ORDER BY case_id ASC
    """
    params = [rule_version, min_seq_len_clean]

    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    with get_conn(db_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [int(r["case_id"]) for r in cur.fetchall()]


def fetch_case_events(
    db_cfg: DBConfig,
    case_ids: list[int],
    rule_version: str,
) -> dict[int, list[dict]]:
    """
    event_log에서 case_id별 이벤트를 직접 읽는다.
    새 ETL 테이블을 만들지 않는다.
    """
    if not case_ids:
        return {}

    out: dict[int, list[dict]] = {}
    chunk_size = 500

    with get_conn(db_cfg) as conn:
        with conn.cursor() as cur:
            for i in range(0, len(case_ids), chunk_size):
                chunk = case_ids[i : i + chunk_size]
                placeholders = ",".join(["%s"] * len(chunk))

                sql = f"""
                    SELECT
                        case_id,
                        source_event_pk,
                        ts,
                        activity,
                        activity_l1,
                        activity_l2,
                        event_type,
                        interaction_type,
                        page_url,
                        page_title,
                        api_path,
                        api_method,
                        api_status_code,
                        element_tag,
                        associated_label,
                        element_text
                    FROM event_log
                    WHERE case_id IN ({placeholders})
                      AND activity_rule_version = %s
                    ORDER BY case_id ASC, ts ASC, source_event_pk ASC
                """

                cur.execute(sql, [*chunk, rule_version])
                rows = cur.fetchall()

                for r in rows:
                    cid = int(r["case_id"])
                    out.setdefault(cid, []).append(r)

    return out


def fetch_case_clusters(
    db_cfg: DBConfig,
    model_version: str,
) -> dict[int, int]:
    """
    HDBSCAN variant를 pseudo-label 또는 sampling 정보로 사용하기 위한 함수.
    학습 필수는 아니지만 contrastive learning, 대표 case 선별에 활용 가능.
    """
    sql = """
        SELECT case_id, variant_id
        FROM case_clusters
        WHERE model_version = %s
    """

    with get_conn(db_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (model_version,))
            rows = cur.fetchall()

    return {int(r["case_id"]): int(r["variant_id"]) for r in rows}