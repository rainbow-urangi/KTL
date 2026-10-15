"""Read-only evaluation of local evidence; never writes into model/ or test-data/."""
import csv
import hashlib
import io
import json
import math
import subprocess
import unicodedata
from collections import Counter

REFERENCE = {"events": 32273, "latent_segments": 5167, "latent_workflows": 563,
             "process_instances": 1619, "process_models": 12}
METRICS = {
    "M01": ("Collection Accuracy", "test-data/m01.json", 100, ">="),
    "M02": ("Process Map Accuracy and Completeness", "test-data/m02.json", 5, ">="),
    "M03": ("Test Scenario Automatic Generation Rate", "test-data/m03.json", 20, ">="),
    "M04": ("Automated Execution Success Rate", "TD-08 fixed Selenium/Python scripts", 20, ">="),
    "M05": ("AI Data Cleaning F1 Score", "test-data/m05.json", 200, ">="),
    "M06": ("Workflow Clustering Quality", "model/v6_2/frozen/run_manifest.json", 563, "<="),
    "M07": ("LLM Generated Code Validity and Accuracy", "results/M03/latest.json", None, ">=")
}


class EvaluationError(Exception):
    def __init__(self, message, status="NOT_CONFIGURED"):
        super().__init__(message)
        self.status = status


def require(condition, message):
    if not condition:
        raise EvaluationError(message, "ERROR")


def read_json(path):
    if not path.is_file():
        raise EvaluationError(f"Missing input: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise EvaluationError(f"Invalid JSON: {path.name}", "ERROR") from exc


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_list(value, label):
    require(isinstance(value, list) and all(isinstance(x, dict) for x in value),
            f"{label} must be an array of objects")
    return value


def unique_ids(rows, label):
    ids = [row.get("id") for row in rows]
    require(all(isinstance(x, str) and x.strip() for x in ids), f"{label}: nonempty string IDs required")
    require(len(ids) == len(set(ids)), f"{label}: duplicate IDs")
    return set(ids)


def call_adapter(config, name, payload, cwd):
    command = config.get("adapters", {}).get(name)
    if not command:
        raise EvaluationError(f"Configure the {name} adapter in backend/config.json")
    require(isinstance(command, list) and all(isinstance(x, str) for x in command),
            f"{name} adapter must be an argv array")
    try:
        completed = subprocess.run(command, input=json.dumps(payload, ensure_ascii=False),
                                   text=True, capture_output=True, cwd=cwd,
                                   timeout=config.get("adapter_timeout_seconds", 120), check=False)
    except subprocess.TimeoutExpired as exc:
        raise EvaluationError(f"{name} adapter timed out", "ERROR") from exc
    except OSError as exc:
        raise EvaluationError(f"Cannot start {name} adapter: {exc}", "ERROR") from exc
    if completed.returncode:
        raise EvaluationError(f"{name} adapter exited with code {completed.returncode}", "ERROR")
    try:
        value = json.loads(completed.stdout)
    except ValueError as exc:
        raise EvaluationError(f"{name} adapter did not return JSON", "ERROR") from exc
    require(isinstance(value, dict), f"{name} adapter response must be an object")
    return value


def csv_evidence(rows):
    stream = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ["status"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return "\ufeff" + stream.getvalue()


class M02Evaluator:
    """직접 절차명을 일대일 비교합니다. 보조 증거는 정답으로 집계하지 않습니다."""
    version = 'm02-evaluator-v1.1'

    @staticmethod
    def canonical_label(label):
        require(label is None or isinstance(label, str), 'M02 label must be a string or null')
        return ''.join(c for c in unicodedata.normalize('NFKC', label or '').casefold() if not c.isspace()).strip()

    def __init__(self, alias_contract=None):
        self.aliases = {}
        if alias_contract is None:
            return
        require(isinstance(alias_contract, dict) and isinstance(alias_contract.get('version'), str)
                and bool(alias_contract['version'].strip()), 'Alias version required')
        rows = object_list(alias_contract.get('aliases'), 'aliases')
        for row in rows:
            canonical = self.canonical_label(row.get('canonical'))
            require(bool(canonical), 'Nonempty alias canonical required')
            accepted = row.get('accepted')
            require(isinstance(accepted, list) and all(isinstance(v, str) for v in accepted), 'Accepted aliases must be strings')
            for label in [row['canonical'], *accepted]:
                key = self.canonical_label(label)
                require(bool(key), 'Empty alias is not allowed')
                require(key not in self.aliases or self.aliases[key] == canonical, 'Conflicting alias mapping')
                self.aliases[key] = canonical

    def normalized_label(self, label):
        canonical = self.canonical_label(label)
        return self.aliases.get(canonical, canonical)

    def evaluate(self, process_result, ground_truth):
        actual = object_list(process_result.get('processes'), 'processes')
        truth = object_list(ground_truth.get('processes'), 'ground_truth processes')
        unique_ids(actual, 'processes'); unique_ids(truth, 'ground_truth')
        require(bool(truth), 'Ground Truth is empty')
        def procedures(process):
            rows = object_list(process.get('procedures'), 'procedures')
            unique_ids(rows, 'procedures')
            require(all(r.get('label') is None or isinstance(r['label'], str) for r in rows), 'Procedure label must be a string or null')
            return rows
        detected = {p['id']: procedures(p) for p in actual}
        required = {p['id']: procedures(p) for p in truth}
        require(all(required.values()), 'Required procedures are empty')
        normalize = self.normalized_label
        rows, matches = [], 0
        for pid in dict.fromkeys([*required, *detected]):
            available = list(detected.get(pid, []))
            for gt in required.get(pid, []):
                hit = next((r for r in available if r.get('evidence_type', 'direct') == 'direct'
                            and bool(normalize(gt.get('label')))
                            and normalize(r.get('label')) == normalize(gt.get('label'))), None)
                if hit is not None:
                    available.remove(hit); matches += 1
                rows.append({'process_id': pid, 'ground_truth_step': gt.get('label') or '',
                             'detected_step': hit.get('label') if hit else '',
                             'detected_id': hit['id'] if hit else '', 'direct_match': hit is not None})
            rows.extend({'process_id': pid, 'ground_truth_step': '', 'detected_step': r.get('label') or '',
                         'detected_id': r['id'], 'direct_match': False} for r in available)
        evaluated = sum(map(len, detected.values())); defined = sum(map(len, required.values()))
        require(evaluated > 0, 'No evaluated procedures; a score cannot be calculated')
        accuracy = 100 * matches / evaluated; completeness = 100 * matches / defined
        return math.sqrt(accuracy * completeness), len(truth), {
            'accuracy': accuracy, 'completeness': completeness, 'correctly_mapped': matches,
            'evaluated_procedures': evaluated, 'included_required': matches, 'defined_required': defined,
            'formula': 'sqrt(Accuracy * Completeness)', 'auxiliary_evidence_counted': False,
            'matching_method': 'NFKC + casefold + Unicode whitespace removal + approved aliases; same scenario, one-to-one direct match'}, rows


class M05Evaluator:
    """REMOVE를 양성으로 평가하며 F1은 0~1 범위입니다."""
    def evaluate(self, events, predictions):
        object_list(events, 'events'); object_list(predictions, 'predictions')
        require(bool(events), 'Events are empty')
        require(unique_ids(events, 'events') == unique_ids(predictions, 'predictions'), 'Prediction IDs must match event IDs')
        require(all(r.get('label') in {'KEEP', 'REMOVE'} for r in events + predictions), 'Invalid label')
        predicted = {p['id']: p['label'] for p in predictions}
        counts = Counter(('TP' if e['label'] == 'REMOVE' else 'FP') if predicted[e['id']] == 'REMOVE'
                         else ('FN' if e['label'] == 'REMOVE' else 'TN') for e in events)
        tp, fp, fn, tn = (counts[k] for k in ('TP', 'FP', 'FN', 'TN'))
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0
        return f1, len(events), dict(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn, tn=tn, positive_class='REMOVE'), [
            {'event_id': e['id'], 'expected': e['label'], 'predicted': predicted[e['id']],
             'category': e.get('category', '')} for e in events]


class M06Evaluator:
    """입력 feature와 고정 label로만 DBI를 계산합니다."""
    def evaluate(self, features, labels):
        require(isinstance(features, list) and isinstance(labels, list) and len(features) == len(labels) and bool(features), 'Feature/label length mismatch')
        require(all(isinstance(v, list) and v for v in features), 'Nonempty feature vectors required')
        require(len({len(v) for v in features}) == 1, 'Feature dimension mismatch')
        require(all(type(x) in (int, float) and math.isfinite(x) for v in features for x in v), 'Finite numeric features required')
        require(all(type(k) in (str, int) for k in labels), 'Invalid cluster labels')
        clusters = {}
        for vector, label in zip(features, labels):
            clusters.setdefault(label, []).append(vector)
        require(2 <= len(clusters) < len(features), 'DBI requires 2 <= clusters < samples')
        centroids = {k: [sum(c) / len(v) for c in zip(*v)] for k, v in clusters.items()}
        scatter = {k: sum(math.dist(v, centroids[k]) for v in values) / len(values) for k, values in clusters.items()}
        rows = []
        for k in clusters:
            ratios = []
            for other in clusters:
                if other == k:
                    continue
                distance = math.dist(centroids[k], centroids[other])
                require(distance > 0, 'DBI undefined for coincident centroids')
                ratios.append((scatter[k] + scatter[other]) / distance)
            rows.append({'cluster': k, 'workflow_count': len(clusters[k]), 'scatter': scatter[k], 'max_ratio': max(ratios)})
        return sum(r['max_ratio'] for r in rows) / len(rows), len(features), {'cluster_count': len(clusters), 'dimensions': len(features[0]), 'distance': 'Euclidean'}, rows
