from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

from model import EventTransformerEncoder
from vocab import Vocab


class CLIIntegrationTests(unittest.TestCase):
    def test_csv_fine_tune_and_workflow_inference(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            model_dir = temp / "model"
            model_dir.mkdir()
            csv_path = temp / "events.csv"
            mapping_path = temp / "mapping.json"
            labels_path = temp / "labels.csv"
            output_path = temp / "workflows.jsonl"

            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=("case", "time", "action"))
                writer.writeheader()
                for case_id in (1, 2):
                    for index, action in enumerate(("NAV:/list", "CLICK:new", "SUBMIT:save")):
                        writer.writerow(
                            {"case": case_id, "time": f"2026-01-01T00:00:0{index}", "action": action}
                        )
            mapping_path.write_text(
                json.dumps({"case_id": "case", "ts": "time", "activity": "action"}),
                encoding="utf-8",
            )
            labels_path.write_text(
                "case_id,event_index,is_step_start,abstract_step_type\n"
                "1,0,1,NAVIGATION_OR_ACCESS\n1,1,1,CREATE_OR_REGISTER\n1,2,0,SUBMIT_OR_SAVE\n"
                "2,0,1,NAVIGATION_OR_ACCESS\n2,1,1,CREATE_OR_REGISTER\n2,2,0,SUBMIT_OR_SAVE\n",
                encoding="utf-8",
            )

            vocabs = {
                "activity": Vocab.build(["NAV:/list", "CLICK:new", "SUBMIT:save"]),
                "l1": Vocab.build(["none"]),
                "api_method": Vocab.build(["none"]),
                "status": Vocab.build(["none"]),
                "delta": Vocab.build(["none", "lt_1s"]),
            }
            for name, vocab in vocabs.items():
                vocab.save(str(model_dir / f"{name}_vocab.json"))
            encoder = EventTransformerEncoder(
                len(vocabs["activity"]), len(vocabs["l1"]),
                len(vocabs["api_method"]), len(vocabs["status"]),
                len(vocabs["delta"]), d_model=8, nhead=2, num_layers=1,
                dim_feedforward=16, max_len=8,
            )
            torch.save(
                {
                    "model_state_dict": encoder.state_dict(),
                    "train_config": {
                        "d_model": 8, "nhead": 2, "num_layers": 1,
                        "dim_feedforward": 16, "dropout": 0.1, "max_seq_len": 8,
                    },
                },
                model_dir / "model.pt",
            )
            env = {
                **os.environ,
                "MODEL_DIR": str(model_dir),
                "DATA_SOURCE": "csv",
                "CSV_PATH": str(csv_path),
                "COLUMN_MAPPING_PATH": str(mapping_path),
                "MIN_SEQ_LEN_CLEAN": "1",
                "BATCH_SIZE": "2",
            }
            subprocess.run(
                [sys.executable, "train_step_extractor.py", "--labels", str(labels_path), "--epochs", "1"],
                cwd=root, env=env, check=True, capture_output=True, text=True,
            )
            step_model = model_dir / "step_extractor.pt"
            self.assertTrue(step_model.is_file())
            subprocess.run(
                [
                    sys.executable, "infer_workflows.py", "--step-model", str(step_model),
                    "--output", str(output_path),
                ],
                cwd=root, env=env, check=True, capture_output=True, text=True,
            )
            workflows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(workflows), 2)
            self.assertTrue(workflows[0]["steps"])
            self.assertIn("evidence_activities", workflows[0]["steps"][0])


if __name__ == "__main__":
    unittest.main()
