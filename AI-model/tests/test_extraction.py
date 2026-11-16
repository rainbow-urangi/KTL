from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import torch

from adapters.csv_adapter import CSVCaseAdapter, generic_activity, normalize_case_id
from extraction.high_level_extractor import HighLevelBusinessExtractor
from extraction.segmentation import boundary_probs_to_segments
from extraction.workflow_exporter import export_workflows_jsonl
from extraction.workflow_schema import WorkflowPrediction, WorkflowStep
from model import EventTransformerEncoder
from train_step_extractor import (
    IGNORE_STEP_TYPE,
    StepLabeledDataset,
    collate_step_batch,
    compute_loss,
    load_labels,
)
from dataset import BrowserEventDataset, CaseSequence
from vocab import Vocab


class CSVAdapterTests(unittest.TestCase):
    def test_generic_activity_rules(self):
        self.assertEqual(
            generic_activity({"event_type": "PAGE_VIEW", "page_url": "https://x.test/orders?q=1"}),
            "NAV:/orders",
        )
        self.assertEqual(
            generic_activity({"api_path": "/orders", "api_method": "get", "api_status_code": "201"}),
            "API:GET_/orders_2xx",
        )
        self.assertEqual(
            generic_activity({"interaction_type": "click", "associated_label": "Search"}),
            "CLICK:Search",
        )

    def test_csv_load_sort_dedupe_and_string_case_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=("session", "time", "kind", "label"))
                writer.writeheader()
                writer.writerows(
                    [
                        {"session": "ABC", "time": "2026-01-01T00:00:02", "kind": "click", "label": "B"},
                        {"session": "ABC", "time": "2026-01-01T00:00:01", "kind": "click", "label": "A"},
                        {"session": "ABC", "time": "2026-01-01T00:00:03", "kind": "click", "label": "B"},
                    ]
                )
            adapter = CSVCaseAdapter(
                str(path),
                {"case_id": "session", "ts": "time", "interaction_type": "kind", "associated_label": "label"},
                min_seq_len=1,
            )
            cases = adapter.load_cases()
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].case_id, normalize_case_id("ABC"))
            self.assertEqual(
                [row["activity"] for row in cases[0].rows],
                ["CLICK:A", "CLICK:B"],
            )


class ExtractionTests(unittest.TestCase):
    def test_segmentation_and_short_tail_merge(self):
        self.assertEqual(
            boundary_probs_to_segments([0.1, 0.9, 0.1, 0.8], 0.5),
            [
                {"step_order": 1, "start_idx": 0, "end_idx": 0},
                {"step_order": 2, "start_idx": 1, "end_idx": 2},
                {"step_order": 3, "start_idx": 3, "end_idx": 3},
            ],
        )
        self.assertEqual(
            boundary_probs_to_segments([0.1, 0.1, 0.9, 0.1, 0.9], 0.5, min_step_len=2),
            [
                {"step_order": 1, "start_idx": 0, "end_idx": 1},
                {"step_order": 2, "start_idx": 2, "end_idx": 4},
            ],
        )

    def test_model_output_shapes(self):
        encoder = EventTransformerEncoder(12, 6, 5, 5, 8, d_model=8, nhead=2, num_layers=1, dim_feedforward=16, max_len=8)
        model = HighLevelBusinessExtractor(encoder, num_step_types=11)
        ids = torch.ones((2, 4), dtype=torch.long)
        output = model(ids, ids, ids, ids, ids, attention_mask=torch.zeros_like(ids).bool())
        self.assertEqual(output["boundary_logits"].shape, (2, 4))
        self.assertEqual(output["step_type_logits"].shape, (2, 4, 11))

    def test_jsonl_export(self):
        workflow = WorkflowPrediction(
            case_id=1,
            model_version="test",
            steps=[WorkflowStep(1, "FORM_INPUT", 0, 1, 0.8, ["INPUT:name"])],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "workflows.jsonl"
            export_workflows_jsonl([workflow], str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["steps"][0]["end_idx"], 1)


class StepTrainingTests(unittest.TestCase):
    def _vocabs(self):
        return {
            "activity": Vocab.build(["CLICK:A", "CLICK:B"]),
            "l1": Vocab.build(["click"]),
            "api_method": Vocab.build(["none"]),
            "status": Vocab.build(["none"]),
            "delta": Vocab.build(["none", "lt_1s"]),
        }

    def test_empty_step_types_are_masked_and_boundary_backpropagates(self):
        vocabs = self._vocabs()
        cases = [
            CaseSequence(
                case_id=1,
                rows=[
                    {"activity": "CLICK:A", "activity_l1": "click"},
                    {"activity": "CLICK:B", "activity_l1": "click"},
                ],
            )
        ]
        base = BrowserEventDataset(
            cases, vocabs["activity"], vocabs["l1"], vocabs["api_method"],
            vocabs["status"], vocabs["delta"], max_len=8, mask_prob=0.0,
            mode="inference",
        )
        dataset = StepLabeledDataset(base, {1: {0: (1.0, IGNORE_STEP_TYPE), 1: (0.0, IGNORE_STEP_TYPE)}})
        batch = collate_step_batch([dataset[0]], vocabs["activity"].pad_id)
        encoder = EventTransformerEncoder(
            len(vocabs["activity"]), len(vocabs["l1"]),
            len(vocabs["api_method"]), len(vocabs["status"]),
            len(vocabs["delta"]), d_model=8, nhead=2, num_layers=1,
            dim_feedforward=16, max_len=8,
        )
        model = HighLevelBusinessExtractor(encoder, 11)
        loss, boundary_loss, type_loss, _, _, type_mask = compute_loss(
            model, batch, torch.nn.BCEWithLogitsLoss(), torch.nn.CrossEntropyLoss()
        )
        self.assertFalse(type_mask.any())
        self.assertEqual(float(type_loss), 0.0)
        self.assertGreater(float(boundary_loss), 0.0)
        loss.backward()
        self.assertIsNotNone(model.encoder.boundary_head.weight.grad)

    def test_label_loader_accepts_blank_abstract_type(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            path.write_text(
                "case_id,event_index,is_step_start,abstract_step_type\n"
                "ABC,0,1,\nABC,1,0,FORM_INPUT\n",
                encoding="utf-8",
            )
            labels = load_labels(str(path))
            case_labels = labels[normalize_case_id("ABC")]
            self.assertEqual(case_labels[0][1], IGNORE_STEP_TYPE)
            self.assertGreaterEqual(case_labels[1][1], 0)


if __name__ == "__main__":
    unittest.main()
