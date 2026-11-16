from __future__ import annotations

from dataset import CaseSequence, rle_dedupe_rows
from db import fetch_candidate_case_ids, fetch_case_clusters, fetch_case_events

from .base_adapter import BaseCaseAdapter


class CurrentDBCaseAdapter(BaseCaseAdapter):
    def __init__(self, db_cfg, train_cfg):
        self.db_cfg = db_cfg
        self.train_cfg = train_cfg

    def load_cases(self) -> list[CaseSequence]:
        case_ids = fetch_candidate_case_ids(
            db_cfg=self.db_cfg,
            rule_version=self.train_cfg.rule_version,
            min_seq_len_clean=self.train_cfg.min_seq_len_clean,
        )
        print(f"[data] candidate cases={len(case_ids)}")

        events_by_case = fetch_case_events(
            db_cfg=self.db_cfg,
            case_ids=case_ids,
            rule_version=self.train_cfg.rule_version,
        )

        try:
            clusters = fetch_case_clusters(
                db_cfg=self.db_cfg,
                model_version=self.train_cfg.cluster_model_version,
            )
        except Exception as exc:
            # Clusters are optional metadata. Missing tables must not block training.
            print(f"[warning] case_clusters unavailable; continuing without variants: {exc}")
            clusters = {}

        cases = []
        for case_id in case_ids:
            rows = rle_dedupe_rows(events_by_case.get(case_id, []))
            if len(rows) < self.train_cfg.min_seq_len_clean:
                continue
            cases.append(
                CaseSequence(
                    case_id=case_id,
                    rows=rows[: self.train_cfg.max_seq_len],
                    variant_id=clusters.get(case_id),
                )
            )

        print(f"[data] usable cases={len(cases)}")
        return cases
