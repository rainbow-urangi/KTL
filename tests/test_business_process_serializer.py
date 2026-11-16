import copy
import inspect
import unittest
from backend.business_process_serializer import serialize, canonical_bytes

class BusinessSerializerTests(unittest.TestCase):
    def fixture(self):
        actions = [("submit_save", ""), ("api_confirmation", "POST"),
                   ("detail_close", ""), ("api_confirmation", "GET"),
                   ("api_failure", "PATCH"), ("future_action", "")]
        nodes = [dict(node_id=f"n{i}", process_model_id="process-any",
            action=a, http_method=m, normalized_endpoint="/generic", page_path="/any",
            target_role="button", source_event_evidence=[f"event-{i}"])
            for i, (a, m) in enumerate(actions)]
        models = [dict(process_model_id="process-any", canonical_instance_id="instance-any",
            canonical_node_sequence=[n["node_id"] for n in nodes] + ["n0"])]
        occurrences = [dict(next(n for n in nodes if n["node_id"] == nid),
            process_instance_id="instance-any", step_order=order,
            source_event_evidence=[f"occurrence-{order}"]) for order, nid in enumerate(models[0]["canonical_node_sequence"], 1)]
        return models, nodes, occurrences

    def test_conservation_repeat_provenance_and_no_input_mutation(self):
        models, nodes, occurrences = self.fixture()
        before = copy.deepcopy((models, nodes))
        result = serialize(models, nodes, occurrences)
        steps = result["processes"][0]["business_steps"]
        self.assertEqual(len(steps), 4)
        self.assertEqual(result["generated_business_step_count"], len(steps))
        self.assertEqual(result["auxiliary_exclusions"], [])
        for step, nid in zip(steps, ["n0", "n2", "n5", "n0"]):
            node = next(n for n in nodes if n["node_id"] == nid)
            self.assertEqual(step["source_node_ids"], [nid])
            self.assertEqual(step["source_event_ids"], occurrences[step["source_occurrence_order"]-1]["source_event_evidence"])
            self.assertEqual(step["evidence"], [occurrences[step["source_occurrence_order"]-1]])
        self.assertEqual((models, nodes), before)

    def test_save_http_and_close_are_separate_and_methods_preserved(self):
        result = serialize(*self.fixture())
        steps = result["processes"][0]["business_steps"]
        self.assertEqual([s["action_type"] for s in steps],
            ["SUBMIT_SAVE", "DETAIL_CLOSE", "UNRESOLVED", "SUBMIT_SAVE"])
        steps = result["processes"][0]["unlinked_technical_evidence"]
        self.assertEqual(steps[2]["source_action"], "api_failure")
        self.assertEqual(steps[2]["http_method"], "PATCH")
        self.assertEqual(result["processes"][0]["business_steps"][2]["action_type"], "UNRESOLVED")

    def test_deterministic_and_generic_across_arbitrary_business_identity(self):
        models, nodes, occurrences = self.fixture()
        self.assertEqual(canonical_bytes(serialize(models, nodes, occurrences)), canonical_bytes(serialize(models, nodes, occurrences)))
        original = serialize(models, nodes, occurrences)
        models[0]["process_model_id"] = "arbitrary-new-business"
        for node in nodes:
            node["process_model_id"] = "arbitrary-new-business"
        for occurrence in occurrences:
            occurrence["process_model_id"] = "arbitrary-new-business"
        other = serialize(models, nodes, occurrences)
        self.assertEqual([s["action_type"] for s in original["processes"][0]["business_steps"]],
                         [s["action_type"] for s in other["processes"][0]["business_steps"]])

    def test_no_gt_input_or_io_and_noncanonical_evidence_preserved(self):
        self.assertEqual(list(inspect.signature(serialize).parameters), ["models", "nodes", "occurrences"])
        source = inspect.getsource(serialize)
        self.assertNotIn("open(", source)
        self.assertNotIn("read_json", source)
        models, nodes, occurrences = self.fixture()
        nodes.append(dict(nodes[0], node_id="noncanonical"))
        result = serialize(models, nodes, occurrences)
        self.assertEqual(len(result["graph_evidence"]), 7)
        self.assertEqual(result["generated_business_step_count"], 4)

    def test_invalid_references_rejected(self):
        models, nodes, occurrences = self.fixture()
        with self.assertRaises(ValueError):
            serialize(models, nodes + [nodes[0]], occurrences)
        models[0]["canonical_node_sequence"].append("missing")
        with self.assertRaises(ValueError):
            serialize(models, nodes, occurrences)

    def test_occurrence_collisions_missing_and_mismatch_rejected(self):
        models, nodes, occurrences = self.fixture()
        for bad in (occurrences + [dict(occurrences[0])], occurrences[1:],
                    [dict(occurrences[0], node_id="different")] + occurrences[1:],
                    [dict(occurrences[0], process_model_id="different")] + occurrences[1:],
                    [dict(occurrences[0], source_event_evidence=[])] + occurrences[1:]):
            with self.assertRaises(ValueError):
                serialize(models, nodes, bad)

    def test_noncanonical_instance_cannot_replace_canonical_occurrence(self):
        models, nodes, occurrences = self.fixture()
        unrelated = dict(occurrences[0], process_instance_id="other", source_event_evidence=["other-event"])
        result = serialize(models, nodes, occurrences + [unrelated])
        steps = result["processes"][0]["business_steps"]
        self.assertNotEqual(steps[0]["source_event_ids"], steps[-1]["source_event_ids"])
        self.assertEqual(steps[0]["source_event_ids"], ["occurrence-1"])
        self.assertEqual(steps[-1]["source_event_ids"], ["occurrence-7"])
        self.assertEqual(result["processes"][0]["unlinked_technical_evidence"][0]["semantic_status"], "UNRESOLVED_TECHNICAL_EVIDENCE")
        result["processes"][0]["business_steps"][0]["evidence"][0]["source_event_evidence"].append("mutated")
        self.assertEqual(occurrences[0]["source_event_evidence"], ["occurrence-1"])

    def test_partition_all_occurrences_and_preserve_unknown_http_methods(self):
        models, nodes, occurrences = self.fixture()
        for method, expected in [("GET", "HTTP_READ"), ("HEAD", "HTTP_READ"),
                ("OPTIONS", "HTTP_READ"), ("POST", "HTTP_WRITE"),
                ("PUT", "HTTP_WRITE"), ("PATCH", "HTTP_WRITE"),
                ("DELETE", "HTTP_WRITE"), ("CONNECT", "HTTP_UNKNOWN")]:
            nodes[1]["http_method"] = method
            occurrences[1]["http_method"] = method
            before = copy.deepcopy((models, nodes, occurrences))
            result = serialize(models, nodes, occurrences)
            process = result["processes"][0]
            business, technical = process["business_steps"], process["unlinked_technical_evidence"]
            positions = [r["source_occurrence_order"] for r in business + technical]
            self.assertEqual(sorted(positions), list(range(1, 8)))
            self.assertEqual(len(set(positions)), 7)
            self.assertEqual([r["step_order"] for r in business], [1, 2, 3, 4])
            self.assertEqual(technical[0]["action_type"], expected)
            self.assertEqual(technical[0]["http_method"], method)
            self.assertEqual(result["technical_evidence_count"], 3)
            self.assertEqual(result["generated_business_step_count"], 4)
            self.assertEqual(result["source_occurrence_evidence"], occurrences)
            for record in technical:
                self.assertIsNone(record["linked_generated_step_id"])
                self.assertNotIn("generated_step_id", record)
                self.assertEqual(record["evidence"][0], occurrences[record["source_occurrence_order"]-1])
            self.assertEqual((models, nodes, occurrences), before)

    def test_http_only_process_retained_without_fabricated_business_step(self):
        models, nodes, occurrences = self.fixture()
        models[0]["canonical_node_sequence"] = ["n1"]
        occurrences = [dict(occurrences[1], step_order=1)]
        result = serialize(models, nodes, occurrences)
        self.assertEqual(len(result["processes"]), 1)
        self.assertEqual(result["generated_business_step_count"], 0)
        self.assertEqual(result["technical_evidence_count"], 1)
