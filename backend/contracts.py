"""외부 모듈 연결 계약. 실제 수집/실행/코드 생성 엔진은 포함하지 않습니다."""
from typing import Protocol
from .evaluators import require, object_list, unique_ids


class CollectorAdapter(Protocol):
    def collect(self, required_events: list) -> dict:
        """Return collected_events with scenario_id, execution_id, event_id, event_type."""
        ...


class TestRunnerAdapter(Protocol):
    def execute(self, scenarios: list) -> dict:
        """Return every attempt including failures: scenario_id, success, evidence."""
        ...


class LLMCodeGeneratorAdapter(Protocol):
    def generate(self, scenario: dict) -> dict:
        """Return code, language=python, framework=selenium, model, version."""
        ...


class CodeValidationAdapter(Protocol):
    def validate(self, code: dict) -> dict:
        """Return syntax_pass and execution_pass; both are required for success."""
        ...


class CleaningModelAdapter(Protocol):
    def predict(self, events: list) -> dict:
        """Input: id/features only. Output: predictions[{id,label}], model_version."""
        ...


class ScenarioGeneratorAdapter(Protocol):
    def generate(self, business_unit: dict) -> dict:
        """Return a StructuredScenario; no Ground Truth may enter this adapter."""
        ...


def validate_business_unit(unit):
    require(isinstance(unit, dict), 'BusinessUnit must be an object')
    require(all(isinstance(unit.get(k), str) and unit[k].strip() for k in ('id', 'name')), 'BusinessUnit id/name required')
    steps = object_list(unit.get('steps'), 'BusinessUnit steps')
    require(bool(steps), 'BusinessUnit steps required')
    unique_ids(steps, 'BusinessUnit steps')
    require(all(isinstance(s.get('label'), str) and s['label'].strip() for s in steps), 'Step label required')
    require(not {'ground_truth', 'expected_label', 'label'}.intersection(unit), 'Ground Truth is evaluation-only')
    return unit


def validate_scenario(scenario, unit):
    validate_business_unit(unit)
    require(isinstance(scenario, dict), 'StructuredScenario must be an object')
    require(scenario.get('business_unit_id') == unit['id'], 'Business unit mismatch')
    require(all(isinstance(scenario.get(k), str) and scenario[k].strip() for k in ('id', 'name', 'generator_version')), 'Scenario metadata required')
    steps = object_list(scenario.get('steps'), 'Scenario steps')
    require(bool(steps), 'Scenario steps required'); unique_ids(steps, 'Scenario steps')
    require(all(all(isinstance(s.get(k), str) and s[k].strip() for k in ('action', 'expected_outcome')) for s in steps), 'Action and expected outcome required')
    return scenario


def cleaning_payload(events):
    forbidden = {'label', 'category', 'ground_truth', 'expected_label', 'prediction'}
    def clean(value):
        if isinstance(value, dict):
            return not forbidden.intersection(str(k).lower() for k in value) and all(clean(v) for v in value.values())
        return all(clean(v) for v in value) if isinstance(value, list) else True
    object_list(events, 'events'); unique_ids(events, 'events')
    require(all(isinstance(e.get('features'), dict) and clean(e['features']) for e in events), 'Features must not contain Ground Truth')
    return {'events': [{'id': e['id'], 'features': e['features']} for e in events]}
