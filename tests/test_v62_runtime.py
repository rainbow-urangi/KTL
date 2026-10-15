"""Preprocessing recovery, schema and provenance tests only; no model forward."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model.v6_2.inference import loader
from model.v6_2.inference.schema import validate_csvs, EVENT_REQUIRED
from scripts.recover_v62_runtime import ROOT, build_sidecars, notebook_namespace, sha256


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Performs two independent reads/recoveries and all checkpoint comparisons.
        cls.recovered = build_sidecars()

    def test_recovered_vocabularies_equal_saved_runtime(self):
        saved = json.loads((ROOT / "model/v6_2/runtime/categorical_vocabs.json").read_text())
        self.assertEqual(self.recovered["categorical_vocabs.json"], saved)
        for mapping in saved.values():
            self.assertEqual(mapping["<PAD>"], 0)
            self.assertEqual(mapping["<UNK>"], 1)
            self.assertEqual(sorted(mapping.values()), list(range(len(mapping))))

    def test_checkpoint_shape_consistency(self):
        checks = self.recovered["runtime_manifest.json"]["validation"]["categorical_checkpoint_shapes"]
        self.assertEqual({k: v["vocabulary_size"] for k, v in checks.items()},
                         {"event_type": 4, "interaction_type": 19, "element_tag": 8, "api_method": 3})
        self.assertTrue(all(v["checkpoint_shape"] == [v["vocabulary_size"], 128] for v in checks.values()))

    def test_numeric_statistics_are_repeatable_and_match_saved_values(self):
        saved = json.loads((ROOT / "model/v6_2/runtime/feature_stats.json").read_text())
        self.assertEqual(self.recovered["feature_stats.json"], saved)
        self.assertTrue(self.recovered["runtime_manifest.json"]["validation"]["two_recoveries_identical"])

    def test_structural_vocabulary_exact_match(self):
        self.assertTrue(self.recovered["runtime_manifest.json"]["validation"]["structural_vocabulary_exact_match"])

    def test_vocab_tie_order_and_unknown_behavior(self):
        ns, _, _, _ = notebook_namespace()
        vocab = ns["Vocab"](["b", "a", "a", "b", "[NULL]", None])
        self.assertEqual(vocab.itos, ["<PAD>", "<UNK>", "b", "a"])
        self.assertEqual(vocab.enc("new"), 1)
        self.assertEqual(vocab.enc(None), 1)

    def test_feature_contract_excludes_evidence_and_preserves_order(self):
        contract = self.recovered["preprocessing_contract.json"]
        self.assertEqual(contract["categorical_feature_order"], ["event_type", "interaction_type", "element_tag", "api_method"])
        self.assertNotIn("input_data", str(contract["text_fields"]))
        self.assertNotIn("user_id", str(contract["text_fields"]))
        self.assertEqual(contract["semantic_revision_status"], "unresolved")


class LoaderTests(unittest.TestCase):
    def test_loader_verifies_metadata_without_inference(self):
        result = loader.load_runtime()
        self.assertEqual(result["status"], "metadata_verified")
        self.assertFalse(result["inference_ready"])

    def test_manifest_hashes_match_actual_files(self):
        manifest = json.loads((ROOT / "model/v6_2/runtime/runtime_manifest.json").read_text())
        for relative, expected in manifest["source_files_sha256"].items():
            self.assertEqual(sha256(ROOT / relative), expected)
        for name, expected in manifest["sidecar_sha256"].items():
            self.assertEqual(sha256(ROOT / "model/v6_2/runtime" / name), expected)

    def altered_manifest(self, change):
        original = loader.load_json
        def replacement(path):
            data = original(path)
            if path.name == "runtime_manifest.json":
                change(data)
            return data
        return patch.object(loader, "load_json", side_effect=replacement)

    def test_missing_runtime_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(loader.RuntimeMetadataError):
                loader.load_runtime(temp)

    def test_source_hash_mismatch_fails(self):
        def change(data):
            data["source_bundle_sha256"] = "0" * 64
            data["source_files_sha256"][data["source_bundle_path"]] = "0" * 64
        with self.altered_manifest(change), self.assertRaisesRegex(loader.RuntimeMetadataError, "SHA-256 불일치"):
            loader.load_runtime()

    def test_sidecar_hash_mismatch_fails(self):
        with self.altered_manifest(lambda d: d["sidecar_sha256"].update({"feature_stats.json": "0" * 64})), self.assertRaises(loader.RuntimeMetadataError):
            loader.load_runtime()

    def test_wrong_version_fails(self):
        with self.altered_manifest(lambda d: d.update(model_version="v7")), self.assertRaises(loader.RuntimeMetadataError):
            loader.load_runtime()

    def test_missing_required_metadata_fails(self):
        with self.altered_manifest(lambda d: d.pop("reference_dataset_path")), self.assertRaises(loader.RuntimeMetadataError):
            loader.load_runtime()

    def test_missing_sidecar_hash_fails(self):
        with self.altered_manifest(lambda d: d["sidecar_sha256"].pop("feature_stats.json")), self.assertRaises(loader.RuntimeMetadataError):
            loader.load_runtime()


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vocabs = {c: {"<PAD>": 0, "<UNK>": 1, "known": 2} for c in ("event_type", "interaction_type", "element_tag", "api_method")}
        self.event = {name: "" for name in EVENT_REQUIRED}
        self.event.update(event_id="new-event", session_id="new-session", event_time="2030-01-01T12:00:00Z")
        for name in self.vocabs:
            self.event[name] = "known"
        self.session = {"id": "new-session", "user_id": "test-user"}

    def write(self, name, rows):
        path = self.root / name
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def validate(self, events=None, sessions=None, tasks=None):
        return validate_csvs(self.write("events.csv", events if events is not None else [self.event]),
                             self.write("sessions.csv", sessions if sessions is not None else [self.session]),
                             self.vocabs, tasks)

    def codes(self, report):
        return {r["code"] for r in report["errors"]}

    def test_new_identifiers_and_missing_optional_tasks_are_valid(self):
        self.assertTrue(self.validate()["valid"])

    def test_oov_is_reported_without_mutating_vocabulary(self):
        original = copy.deepcopy(self.vocabs)
        self.event["event_type"] = "new-category"
        report = self.validate()
        self.assertTrue(report["valid"])
        self.assertEqual(report["categorical_oov"]["event_type"]["rate"], 1)
        self.assertEqual(self.vocabs, original)

    def test_nullable_categories_are_distinct_from_oov(self):
        self.event["api_method"] = "[NULL]"
        report = self.validate()
        self.assertTrue(report["valid"])
        self.assertEqual(report["categorical_oov"]["api_method"]["null_count"], 1)
        self.assertEqual(report["categorical_oov"]["api_method"]["count"], 0)

    def test_missing_column_and_null_id(self):
        del self.event["event_type"]
        self.event["event_id"] = ""
        self.assertTrue({"missing_column", "null_event_id"} <= self.codes(self.validate()))

    def test_invalid_timestamp(self):
        self.event["event_time"] = "not-a-date"
        self.assertIn("invalid_event_timestamp", self.codes(self.validate()))

    def test_duplicate_event_id(self):
        self.assertIn("duplicate_event_id", self.codes(self.validate([self.event, self.event])))

    def test_unknown_session_reference(self):
        self.event["session_id"] = "absent"
        self.assertIn("unknown_session_reference", self.codes(self.validate()))

    def test_conflicting_user_mapping(self):
        second = {**self.session, "user_id": "different-user"}
        self.assertIn("conflicting_session_user", self.codes(self.validate(sessions=[self.session, second])))

    def test_session_id_column_supported(self):
        self.assertTrue(self.validate(sessions=[{"session_id": "new-session", "user_id": "test-user"}])["valid"])

    def test_numeric_parse_and_negative_values(self):
        self.event.update(api_latency_ms="bad", step_duration_ms="-2")
        self.assertTrue({"numeric_parse_error", "negative_numeric_value"} <= self.codes(self.validate()))

    def test_mixed_timestamp_awareness(self):
        second = {**self.event, "event_id": "other", "event_time": "2030-01-01 12:00:01"}
        self.assertIn("mixed_timestamp_awareness", self.codes(self.validate([self.event, second])))

    def test_tasks_optional_file_does_not_supply_model_features(self):
        tasks = self.write("tasks.csv", [{"id": "task", "task_name": "reference text"}])
        report = self.validate(tasks=tasks)
        self.assertTrue(report["valid"])
        self.assertIn("tasks_not_used_by_model", {w["code"] for w in report["warnings"]})


if __name__ == "__main__":
    unittest.main()
