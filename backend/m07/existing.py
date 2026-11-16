"""Recheck preserved GPT code without a new generation request or code execution."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from ..evaluators import EvaluationError, require


DATASET = 'data/development/m07_existing_codes/20261110-r1'
MANIFEST_SHA256 = '6a0d3b1efa5567bdfac74b4bea906963a0ddffb2a1520d87934a1bc57134da96'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


class ExistingCodeCheck:
    def __init__(self, root, manifest_sha256=None):
        self.root = Path(root).resolve()
        self.directory = self._safe(self.root / DATASET)
        self.manifest_sha256 = manifest_sha256 or MANIFEST_SHA256
        self.lock = threading.RLock()

    def _safe(self, path):
        resolved = Path(path).resolve()
        require(resolved.is_relative_to(self.root), '검사 파일은 프로젝트 내부에 있어야 합니다.')
        return resolved

    def _load(self):
        manifest_raw = self._safe(self.directory / 'manifest.json').read_bytes()
        require(len(manifest_raw) <= 131072 and _sha(manifest_raw) == self.manifest_sha256,
                '기존 코드 목록의 SHA-256이 다릅니다.')
        manifest = _json(manifest_raw)
        require(manifest.get('schema_version') == 'm07-existing-code-batch-v1'
                and manifest.get('code_source') == 'EXISTING_LLM' and manifest.get('required_count') == 10
                and isinstance(manifest.get('source_generation_id'), str)
                and isinstance(manifest.get('cases'), list) and len(manifest['cases']) == 10,
                '기존 문제·코드 10건의 목록이 필요합니다.')
        cases = []
        for row in manifest['cases']:
            require(isinstance(row, dict) and isinstance(row.get('case_id'), str)
                    and re.fullmatch(r'CASE-0(?:0[1-9]|10)', row['case_id'])
                    and all(isinstance(row.get(key), str) and row[key] for key in ('scenario_id', 'workflow_id'))
                    and row.get('expected_syntax_status') in ('PASS', 'FAIL'), '기존 검사 항목 형식이 다릅니다.')
            files = {}
            for kind in ('code', 'scenario', 'contract'):
                relative, digest = row.get(kind + '_path'), row.get(kind + '_sha256')
                require(isinstance(relative, str) and not Path(relative).is_absolute()
                        and isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest),
                        '기존 코드·문제·기대 조건의 경로와 SHA-256이 필요합니다.')
                path = self._safe(self.directory / relative)
                require(path.is_relative_to(self.directory), '기존 코드 묶음 외부의 파일은 읽을 수 없습니다.')
                raw = path.read_bytes()
                require(len(raw) <= 262144 and _sha(raw) == digest, '기존 원본 SHA-256 불일치: ' + kind)
                files[kind] = raw
            problem, contract = _json(files['scenario']), _json(files['contract'])
            require(isinstance(problem, dict) and isinstance(contract, dict)
                    and problem.get('scenario_id') == contract.get('scenario_id') == row.get('scenario_id')
                    and problem.get('workflow_id') == row.get('workflow_id')
                    and isinstance(problem.get('steps'), list) and isinstance(contract.get('steps'), list),
                    '문제·코드·기대 조건의 연결이 다릅니다.')
            cases.append(dict(case_id=row['case_id'], scenario_id=row['scenario_id'], workflow_id=row['workflow_id'],
                              business_unit_id=problem.get('business_unit_id'),
                              scenario_name=problem.get('scenario_name', row['scenario_id']),
                              code=files['code'].decode('utf-8'), code_sha256=row['code_sha256'],
                              problem=problem, expected_results=contract['steps'],
                              expected_syntax_status=row['expected_syntax_status']))
        require(all(len({case[key] for case in cases}) == 10 for key in ('case_id', 'scenario_id', 'workflow_id')),
                '기존 검사 항목은 서로 다른 10건이어야 합니다.')
        return manifest, cases

    def _last(self, cases):
        path = self._safe(self.root / 'data/development/m07_existing_checks/latest.json')
        if not path.is_file():
            return None
        result = _json(path.read_bytes())
        require(result.get('source_manifest_sha256') == self.manifest_sha256
                and result.get('sample_count') == 10 and len(result.get('cases', [])) == 10,
                '보관 검사 결과와 기존 코드 묶음이 다릅니다.')
        require(all(actual.get('case_id') == source['case_id']
                    and actual.get('code_sha256') == source['code_sha256']
                    for actual, source in zip(result['cases'], cases)), '보관 검사 코드의 SHA-256이 다릅니다.')
        return result

    def context(self):
        with self.lock:
            manifest, cases = self._load()
            return dict(code_source='EXISTING_LLM', source_generation_id=manifest['source_generation_id'],
                        source_manifest_sha256=self.manifest_sha256, required_count=10, target=80,
                        new_generation=False, gpt_request_count=0, cases=cases, result=self._last(cases))

    def validate(self):
        with self.lock:
            manifest, cases = self._load()
            rows = []
            for case in cases:
                error = None
                try:
                    # Compile creates a code object only. Do not eval, import or execute it.
                    compile(case['code'].encode('utf-8'), 'script.py', 'exec', dont_inherit=True)
                except (SyntaxError, UnicodeError, ValueError) as exc:
                    error = 'Python 문법 오류' + (' (행 ' + str(exc.lineno) + ')' if isinstance(exc, SyntaxError) else '')
                status = 'FAIL' if error else 'PASS'
                rows.append(dict(case_id=case['case_id'], scenario_id=case['scenario_id'], workflow_id=case['workflow_id'],
                                 code_sha256=case['code_sha256'], syntax_status=status,
                                 expected_syntax_status=case['expected_syntax_status'],
                                 matches_expected=status == case['expected_syntax_status'], error=error))
            self._load()  # Recheck every pinned source before publishing a result.
            passed = sum(row['syntax_status'] == 'PASS' for row in rows)
            result = dict(run_id='M07-CHECK-' + uuid.uuid4().hex, status='COMPLETED', sample_count=10,
                          source_generation_id=manifest['source_generation_id'], source_manifest_sha256=self.manifest_sha256,
                          score=passed * 10, syntax_pass_count=passed, syntax_fail_count=10 - passed, target=80,
                          threshold_met=passed >= 8, matches_expected_count=sum(row['matches_expected'] for row in rows),
                          official_pass=None, new_generation=False, gpt_request_count=0, browser_started_count=0,
                          checked_at=datetime.now(timezone.utc).isoformat(), cases=rows)
            directory = self._safe(self.root / 'data/development/m07_existing_checks')
            directory.mkdir(parents=True, exist_ok=True)
            raw = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
            report = self._safe(directory / (result['run_id'] + '.json'))
            with report.open('xb') as stream:
                stream.write(raw)
            temporary = self._safe(directory / (result['run_id'] + '.latest.tmp'))
            with temporary.open('xb') as stream:
                stream.write(raw)
            os.replace(temporary, self._safe(directory / 'latest.json'))
            return dict(code_source='EXISTING_LLM', source_generation_id=manifest['source_generation_id'],
                        source_manifest_sha256=self.manifest_sha256, required_count=10, target=80,
                        new_generation=False, gpt_request_count=0, cases=cases, result=result)
