import hashlib
import json
import unittest

from backend.m01.scenarios import catalog, SOURCE_SHA256


class M01ScenarioCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog()
        self.scenarios = {row["scenario_id"]: row for row in self.catalog["scenarios"]}

    def test_independent_twenty_businesses_aliases_do_not_add_trials(self):
        self.assertEqual(list(self.scenarios), ["BU%02d" % index for index in range(1, 21)])
        aliases = {alias: row["scenario_id"] for row in self.scenarios.values() for alias in row["aliases"]}
        self.assertEqual(aliases, dict(zip(["CU%02d" % index for index in range(1, 11)],
                                          ["BU02", "BU03", "BU06", "BU07", "BU08", "BU09", "BU10", "BU11", "BU13", "BU14"])))
        self.assertEqual(self.catalog["scenario_count"], 20)
        self.assertFalse(self.catalog["policy"]["login_included"])
        self.assertFalse(self.catalog["approved_for_official"])
        self.assertEqual(self.catalog["source"]["sha256"], SOURCE_SHA256)
        self.assertEqual(self.scenarios["BU14"]["scenario_name"], "BU14 명함 등록")

    def test_hash_binds_full_definition_and_caller_cannot_mutate_later_catalog(self):
        digest = self.catalog.pop("sha256")
        raw = json.dumps(self.catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.scenarios["BU03"]["requirements"][0]["alternatives"][0]["page_url"] = "https://invalid.example/"
        self.assertEqual(catalog()["sha256"], digest)

    def test_each_pdf_step_is_mapped_or_explicitly_unscored(self):
        for scenario in self.scenarios.values():
            mapped = {index for row in scenario["requirements"] for index in row["source_step_indexes"]}
            unscored = {row["index"] for row in scenario["unscored_source_steps"]}
            self.assertEqual(mapped | unscored, set(range(1, len(scenario["source_steps"]) + 1)))
            self.assertFalse(mapped & unscored)
            for row in scenario["unscored_source_steps"]:
                self.assertIn(row["label"], {"종료", "완료 확인"})
            self.assertFalse(scenario["approved_for_official"])
            self.assertTrue(scenario["static_bindings"])

    def test_schedule_requires_separate_title_and_content_input_without_mouse_click(self):
        rows = self.scenarios["BU03"]["requirements"]
        fields = [row for row in rows if row["id"] in {"BU03-TITLE", "BU03-CONTENT"}]
        self.assertEqual(len(fields), 2)
        self.assertEqual({row["alternatives"][0]["target_selector"] for row in fields},
                         {"#schedule-title", "#schedule-description"})
        for row in fields:
            self.assertEqual(row["alternatives"][0]["event_type"], "input")
            self.assertNotIn("interaction_type", row["alternatives"][0])
        self.assertEqual(len(rows), 5)
        self.assertFalse(any("TITLE" in row["id"] and row["alternatives"][0]["event_type"] == "click" for row in rows))

    def test_period_and_anonymous_fields_do_not_use_a_captured_date_or_generic_input(self):
        for identifier in ("BU09", "BU11"):
            period = next(row for row in self.scenarios[identifier]["requirements"] if row["id"].endswith("-PERIOD"))
            self.assertNotIn(":nth", period["alternatives"][0]["target_selector"])
        for identifier in ("BU14", "BU17", "BU20"):
            inputs = [row for row in self.scenarios[identifier]["requirements"] if row["alternatives"][0]["event_type"] == "input"]
            self.assertGreaterEqual(len(inputs), 2)
            targets = [row["alternatives"][0]["target_selector"] for row in inputs]
            self.assertEqual(len(targets), len(set(targets)))
            self.assertTrue(all("section:nth-of-type(" in target and "label:nth-of-type(" in target for target in targets))
            self.assertTrue(self.scenarios[identifier]["binding_preconditions"])

    def test_read_request_does_not_claim_screen_success_or_replace_a_save_click(self):
        for identifier in ("BU01", "BU04", "BU12", "BU15", "BU18"):
            read = next(row for row in self.scenarios[identifier]["requirements"] if row["id"].endswith("-READ"))
            condition = read["alternatives"][0]
            self.assertEqual(condition["event_type"], "network")
            self.assertEqual(condition["api_method"], "GET")
            self.assertNotIn("api_match", condition)
            self.assertIn("성공", read["label"])
        for identifier in ("BU03", "BU07", "BU09", "BU11", "BU14", "BU17", "BU20"):
            save = next(row for row in self.scenarios[identifier]["requirements"] if row["id"].endswith("-SAVE"))
            self.assertEqual({row["event_type"] for row in save["alternatives"]}, {"click"})
            self.assertFalse(any(row.get("api_method") == "POST" for row in save["alternatives"]))


if __name__ == "__main__":
    unittest.main()
