"""Local KTL evaluation service. Run: python3 -m backend.server"""
import argparse
import json
import math
import mimetypes
import os
import re
import socket
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .evaluators import (METRICS, REFERENCE, EvaluationError, M02Evaluator, M05Evaluator, M06Evaluator, csv_evidence, read_json, require, call_adapter)
from .registry import MODES, VERSION, EXTERNAL, INTEGRATIONS
from .run_storage import save_run
from .integration_store import ingest
from .data_sources import V62ReferenceProvider, OfficialEvaluationDataSource
from .contracts import cleaning_payload
from .m01 import M01CsvStore, M01ComparisonStore, MAX_JSON_BYTES
from .session import RuntimeSession

ROOT = Path(__file__).resolve().parents[1]


class LocalHTTPServer(ThreadingHTTPServer):
    # 같은 포트에서 이전 서버와 새 서버가 함께 응답하지 않음
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Service:
    def __init__(self, root=ROOT, session_scoped=False):
        self.root = Path(root).resolve()
        self.lock = threading.Lock()
        self.session = RuntimeSession() if session_scoped else None
        self._m04 = None

    # M04 개발 실행 연결
    def m04(self):
        with self.lock:
            if self._m04 is None:
                from .m04 import M04Manager
                self._m04 = M04Manager(self.root, self.config, session=self.session)
            return self._m04

    def config(self):
        config = read_json(self.root / "backend/config.json")
        require(isinstance(config.get("targets"), dict), "Targets configuration required")
        for metric in METRICS:
            target = config["targets"].get(metric)
            require(target is None or (type(target) in (int, float) and math.isfinite(target) and target >= 0
                    and (metric == "M06" or target <= (1 if metric == "M05" else 100))), "Invalid target: " + metric)
        require(isinstance(config.get('adapters'), dict) and isinstance(config.get('official_manifests'), dict), 'Adapter/manifest configuration required')
        timeout = config.get('adapter_timeout_seconds', 120)
        require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0, 'Positive adapter timeout required')
        from .m03_setup import apply_connection
        return apply_connection(self.root, config)


    def claim_result(self, result):
        if self.session and result.get('run_mode') == 'DEVELOPMENT':
            self.session.claim('RESULT', result.get('run_id'))
        return result

    def latest(self, metric, mode):
        directory = self.root / 'results' / mode.lower()
        latest_path = directory / ('latest-' + metric + '.json')
        if not self.session or mode != 'DEVELOPMENT':
            return read_json(latest_path) if latest_path.is_file() else None
        rows = []
        for identity in self.session.ids('RESULT'):
            if not identity.startswith('DEV-' + metric + '-'):
                continue
            path = directory / identity / 'result.json'
            if path.is_file():
                rows.append(read_json(path))
        return max(rows, key=lambda row: row.get('completed_at') or '', default=None)

    def source(self, mode, config):
        require(mode in MODES, "Mode must be REFERENCE or OFFICIAL")
        if mode == 'DEVELOPMENT':
            from .development_source import DevelopmentDataSource
            return DevelopmentDataSource(self.root)
        return V62ReferenceProvider(self.root) if mode == "REFERENCE" else OfficialEvaluationDataSource(self.root, config)

    def prepare(self, source, metric):
        try:
            return source.prepare(metric)
        except EvaluationError as exc:
            return {"status": exc.status, "inputs": None, "details": {"missing": [str(exc)]}, "error": str(exc)}
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            return {"status": "ERROR", "inputs": None, "details": {}, "error": str(exc)}

    def catalog(self, mode="REFERENCE"):
        config = self.config(); require(mode in MODES, "Invalid mode")
        result = []
        for key, (name, dataset, count, operator) in METRICS.items():
            source = self.source(mode, config); prepared = self.prepare(source, key)
            latest = self.latest(key, mode)
            if key in INTEGRATIONS and latest and latest.get('status') == 'COMPLETED':
                prepared.update(status='COMPLETED',details={'external_result_received':True})
            result.append({"metric_id": key, "metric_name": name, "dataset": source.dataset_id,
                           "expected_sample_count": count, "target": config["targets"].get(key),
                           "operator": operator, "latest": latest, "status": prepared["status"],
                           "details": prepared["details"], "error": prepared.get("error")})
        response = {"run_mode": mode, "metrics": result, "model": {"version": "V6.2", "frozen": True, "reference_counts": REFERENCE}}
        if self.session:
            response.update(server_session_id=self.session.id, server_started_at=self.session.started_at)
        return response

    def ingest(self, metric, payload):
        require(metric in INTEGRATIONS, 'Unsupported integration metric')
        with self.lock:
            config = self.config()
            if (metric == 'M03' and isinstance(payload, dict) and payload.get('run_mode') == 'DEVELOPMENT'
                    and isinstance(payload.get('dataset_id'), str)
                    and payload['dataset_id'].startswith(('m03-mock-development-', 'm03-real-development-'))):
                from .m03_integration import development_context
                context = development_context(self.root, config)
                require(payload['dataset_id'] == context['dataset_id'], 'Development M03 dataset does not match current context')
                require(payload.get('details', {}).get('synthetic') is context['synthetic'], 'M03 source mode does not match current context')
            return self.claim_result(ingest(self.root, config, metric, payload))

    def run(self, metric, mode="REFERENCE"):
        require(mode in MODES and metric in METRICS, "Invalid mode or metric")
        if not self.lock.acquire(blocking=False):
            raise EvaluationError("An evaluation is already running", "RUNNING")
        try:
            config = self.config(); source = self.source(mode, config)
            if metric in INTEGRATIONS:
                latest = self.latest(metric, mode)
                if latest and latest.get('status') == 'COMPLETED':
                    return latest
            if mode == 'DEVELOPMENT':
                if metric in {'M02','M06'}:
                    from .model_runner import EvaluationModelRunner
                    from .model_runner.evaluation import evaluate_run
                    results = evaluate_run(self.root,config,EvaluationModelRunner(self.root).run())
                    for result in results.values():
                        self.claim_result(result)
                    return results[metric]
                prepared=self.prepare(source,metric)
                return self.claim_result(save_run(self.root,metric,mode,config,{'status':prepared['status'],'score':None,'sample_count':None,
                    'dataset_id':source.dataset_id,'source_type':'DEVELOPMENT','details':prepared['details']},[]))
            name, dataset, expected, operator = METRICS[metric]
            run_id = ("REF" if mode == "REFERENCE" else "EVAL") + "-" + metric + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
            run_dir = self.root / "results" / mode.lower() / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            result = {"metric_id": metric, "metric_name": name, "run_id": run_id, "run_mode": mode,
                      "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
                      "dataset_id": source.dataset_id, "source_type": source.source_type,
                      "score": None, "target": config["targets"].get(metric), "operator": operator,
                      "threshold_met": None, "official_pass": None, "pass": None,
                      "sample_count": None, "expected_sample_count": expected,
                      "status": "RUNNING", "details": {}, "error": None,
                      "evaluator_version": M02Evaluator.version if metric == "M02" else VERSION, "model_reference_version": "V6.2" if mode == "REFERENCE" else None}
            def write_json(path, value):
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
                temp.replace(path)
            write_json(run_dir / 'run_manifest.json', result)
            prepared = self.prepare(source, metric)
            result.update(status=prepared['status'], details=prepared['details'], error=prepared.get('error'), dataset_id=source.dataset_id)
            rows = result['details'].pop('rows', [])
            try:
                if prepared['inputs'] is not None:
                    inputs = prepared['inputs']
                    if metric == 'M05':
                        response = call_adapter(config, 'cleaning', cleaning_payload(inputs[0]), self.root)
                        require(response.get('model_version') == config['cleaning_model_version'], 'Cleaning model version mismatch')
                        inputs = (inputs[0], response.get('predictions'))
                    evaluator = M02Evaluator(source.m02_aliases) if metric == 'M02' else {'M05': M05Evaluator, 'M06': M06Evaluator}[metric]()
                    score, count, details, rows = evaluator.evaluate(*inputs)
                    if metric == 'M06' and mode == 'OFFICIAL':
                        try:
                            import sklearn
                            from sklearn.metrics import davies_bouldin_score
                        except ImportError:
                            raise EvaluationError('scikit-learn required for official DBI cross-check', 'NOT_CONFIGURED')
                        reference_score = float(davies_bouldin_score(*inputs))
                        require(abs(score-reference_score) <= 1e-9 * max(1.0, abs(reference_score)), 'DBI cross-check mismatch')
                        details.update(sklearn_dbi=reference_score, sklearn_version=sklearn.__version__, cross_check_pass=True,
                                       feature_space='workflow_embedding_128', measurement_count=1)
                    result.update(score=score, sample_count=count, status='COMPLETED')
                    result['details'].update(details)
                    if result['target'] is not None:
                        result['threshold_met'] = score <= result['target'] if operator == '<=' else score >= result['target']
                        if mode == 'OFFICIAL':
                            result['official_pass'] = result['pass'] = result['threshold_met']
            except EvaluationError as exc:
                result.update(status=exc.status, error=str(exc))
            except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
                result.update(status='ERROR', error=str(exc))
            result['completed_at'] = datetime.now(timezone.utc).isoformat()
            result['input_sha256'] = source.sources
            result['input_paths'] = list(source.sources)
            if metric == 'M02':
                for key in ('selection_method', 'selection_note', 'pairing_file', 'pairing_sha256', 'pairing_fixed_at', 'pairing_pairs', 'alias_file', 'alias_sha256'):
                    result[key] = result['details'].get(key)
            result['model_reference_version'] = result['model_reference_version'] or result['details'].get('model_version')
            result['sample_count'] = result['sample_count'] if result['sample_count'] is not None else result['details'].get('workflow_count')
            result['details']['rows'] = rows
            for key, filename in [('evidence_file','evidence.csv'), ('result_file','result.json'), ('manifest_file','run_manifest.json')]:
                result[key] = f"/api/evaluations/{metric.lower()}/runs/{run_id}/{filename}"
            result['evidence_files'] = ['result.json', 'evidence.csv', 'run_manifest.json']
            (run_dir / 'evidence.csv').write_text(csv_evidence(rows or [{'status': result['status'], 'missing': result['details'].get('missing', []), 'error': result['error']}]), encoding='utf-8')
            write_json(run_dir / 'result.json', result)
            write_json(run_dir / 'run_manifest.json', {k:v for k,v in result.items() if k != 'details'})
            write_json(run_dir.parent / ('latest-' + metric + '.json'), result)
            return result
        finally:
            self.lock.release()


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json; charset=utf-8", attachment=False):
            if isinstance(body, dict) and body.get('status') == 'SESSION_EXPIRED':
                status = 404
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if service.session:
                self.send_header('X-KTL-Server-Session', service.session.id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if attachment:
                filename = attachment if isinstance(attachment, str) else 'evidence.csv'
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
            self.end_headers()
            self.wfile.write(body)

        def trusted_request(self):
            # Local service: prevent cross-site requests and DNS-rebinding hosts.
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin == "http://" + host)

        def do_GET(self):
            if not self.trusted_request():
                return self.reply(403, {"error": "Local same-origin access required"})
            path = urlparse(self.path).path
            try:
                if path.startswith('/api/development/m04/'):
                    try:
                        manager = service.m04()
                        if path == '/api/development/m04/scripts':
                            return self.reply(200, manager.scripts())
                        if path == '/api/development/m04/executions':
                            return self.reply(200, manager.list_runs())
                        screenshot = re.fullmatch(r'/api/development/m04/executions/(M04-RUN-[a-f0-9]{32})/screenshots/(CASE-\d{3})/(before|after)\.png', path)
                        if screenshot:
                            raw, mime = manager.screenshot(screenshot[1], screenshot[2], screenshot[3])
                            return self.reply(200, raw, mime)
                        script = re.fullmatch(r'/api/development/m04/scripts/([0-9a-f]{32})', path)
                        if script:
                            return self.reply(200, manager.read_script(script[1]))
                        execution = re.fullmatch(r'/api/development/m04/executions/(M04-RUN-[0-9a-f]{32})', path)
                        if execution:
                            return self.reply(200, manager.read(execution[1]))
                        artifact = re.fullmatch(r'/api/development/m04/executions/(M04-RUN-[0-9a-f]{32})/artifacts/([a-z.]+)', path)
                        if artifact:
                            raw, content_type = manager.artifact(artifact[1], artifact[2])
                            return self.reply(200, raw, content_type, artifact[2])
                        return self.reply(404, {'status': 'NOT_FOUND', 'error': 'M04 경로를 찾을 수 없습니다.'})
                    except EvaluationError as exc:
                        return self.reply(404 if exc.status == 'NOT_FOUND' else 409 if exc.status in {'RUNNING', 'DUPLICATE_EXECUTION'} else 422,
                                          {'status': exc.status, 'error': str(exc)})
                    except (OSError, ValueError):
                        return self.reply(500, {'status': 'ERROR', 'error': 'M04 실행 기록을 읽을 수 없습니다.'})
                if path == '/api/development/m03/connection':
                    from .m03_setup import connection_state
                    try:
                        with service.lock:
                            state = connection_state(service.root, service.config())
                        return self.reply(200, state)
                    except EvaluationError as exc:
                        return self.reply(422, {'status': exc.status, 'error': str(exc)})
                    except (OSError, ValueError):
                        return self.reply(500, {'status': 'ERROR', 'error': 'M03 연결 설정을 읽을 수 없습니다.'})
                if path == "/api/development/m03/context":
                    from .m03_integration import development_context
                    try:
                        with service.lock:
                            context = development_context(service.root, service.config())
                        return self.reply(200, context)
                    except EvaluationError as exc:
                        return self.reply(422, {"status": exc.status, "error": str(exc)})
                    except OSError:
                        return self.reply(500, {"status": "ERROR", "error": "Unable to prepare development M03 mock context"})
                m03_saved = re.fullmatch(r'/api/development/m03/runs(?:/(DEV-M03-\d{8}T\d{6}-[a-f0-9]{12})/(scenarios|executions))?', path)
                if m03_saved:
                    from .m03_management import list_runs, scenario_state, execution_results
                    try:
                        with service.lock:
                            result = (list_runs(service.root, session=service.session) if not m03_saved[1] else
                                      scenario_state(service.root, m03_saved[1], session=service.session) if m03_saved[2] == 'scenarios' else
                                      execution_results(service.root, m03_saved[1], session=service.session))
                        return self.reply(200, result)
                    except EvaluationError as exc:
                        return self.reply(404 if exc.status == 'NOT_FOUND' else 422,
                                          {'status': exc.status, 'error': str(exc)})
                    except (OSError, ValueError):
                        return self.reply(500, {'status': 'ERROR', 'error': 'M03 저장 기록을 읽을 수 없습니다.'})
                if path in {"/api/development/m01/prod/status", "/api/development/m01/prod/events"}:
                    from .m01 import get_status, query_events, M01ProdError
                    try:
                        if path.endswith("/status"):
                            return self.reply(200, get_status(service.root))
                        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                        require(all(len(values) == 1 for values in query.values()), "Duplicate PROD query parameters")
                        return self.reply(200, query_events(service.root, {key: values[0] for key, values in query.items()}))
                    except M01ProdError as exc:
                        return self.reply(exc.http_status, {"status": "ERROR", "code": exc.code, "error": exc.message})
                    except EvaluationError as exc:
                        return self.reply(400, {"status": exc.status, "error": str(exc)})
                if path == "/api/development/m01/csv":
                    return self.reply(200, M01CsvStore(service.root, session=service.session).list())
                if path == "/api/development/m01/ground-truths":
                    return self.reply(200, M01ComparisonStore(service.root).list_truths())
                truth_match = re.fullmatch(r"/api/development/m01/ground-truths/([0-9a-f]{32})", path)
                if truth_match:
                    try:
                        return self.reply(200, M01ComparisonStore(service.root).read_truth(truth_match[1]))
                    except EvaluationError as exc:
                        return self.reply(404 if exc.status == "NOT_FOUND" else 422,
                                          {"status": exc.status, "error": str(exc)})
                    except OSError:
                        return self.reply(500, {"status": "ERROR", "error": "Unable to read development expected events"})
                comparison_match = re.fullmatch(r"/api/development/m01/comparisons/([0-9a-f]{32})(/evidence.csv|/event-results.csv|/verification)?", path)
                if comparison_match:
                    try:
                        store = M01ComparisonStore(service.root, session=service.session)
                        if comparison_match[2] == "/evidence.csv":
                            return self.reply(200, store.evidence(comparison_match[1]), "text/csv; charset=utf-8", True)
                        if comparison_match[2] == "/event-results.csv":
                            return self.reply(200, store.event_results(comparison_match[1]), "text/csv; charset=utf-8", 'event-results.csv')
                        if comparison_match[2] == "/verification":
                            return self.reply(200, store.verification(comparison_match[1]))
                        return self.reply(200, store.read(comparison_match[1]))
                    except EvaluationError as exc:
                        return self.reply(404 if exc.status == "NOT_FOUND" else 422,
                                          {"status": exc.status, "error": str(exc)})
                    except OSError:
                        return self.reply(500, {"status": "ERROR", "error": "Unable to read development comparison evidence"})
                csv_match = re.fullmatch(r"/api/development/m01/csv/([0-9a-f]{32})(/evidence.csv)?", path)
                if csv_match:
                    query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                    try:
                        options = {"offset": int(query.get("offset", ["0"])[0]),
                                   "limit": int(query.get("limit", ["100"])[0])}
                        if "session_id" in query:
                            options["session_id"] = query["session_id"][0]
                        if "map_target_selector" in query:
                            mapping = query["map_target_selector"][0]
                            require(mapping in {"true", "false"}, "map_target_selector must be true or false")
                            options["map_target_selector"] = mapping == "true"
                        store = M01CsvStore(service.root, session=service.session)
                        if csv_match[2]:
                            return self.reply(200, store.evidence(csv_match[1], **options), "text/csv; charset=utf-8", True)
                        return self.reply(200, store.read(csv_match[1], **options))
                    except ValueError:
                        return self.reply(422, {"status": "ERROR", "error": "Invalid CSV pagination"})
                    except EvaluationError as exc:
                        return self.reply(404 if exc.status == "NOT_FOUND" else 422, {"status": exc.status, "error": str(exc)})
                if path == "/api/evaluations":
                    return self.reply(200, service.catalog(parse_qs(urlparse(self.path).query).get("mode", ["REFERENCE"])[0]))
                match = re.fullmatch(r"/api/evaluations/(m0[1-7])/runs/((?:REF|EVAL|DEV)-M0[1-7]-[0-9]{8}T[0-9]{6}-[0-9a-f]{12})/(evidence.csv|result.json|run_manifest.json|received_payload.json)", path)
                if match:
                    metric, run_id, filename = match.groups()
                    if run_id.split("-")[1] != metric.upper():
                        return self.reply(404, {"error": "Metric mismatch"})
                    if service.session and run_id.startswith('DEV-'):
                        service.session.check('RESULT', run_id)
                    file = service.root / "results" / ({"REF":"reference","EVAL":"official","DEV":"development"}[run_id.split("-")[0]]) / run_id / filename
                    if not file.is_file():
                        return self.reply(404, {"error": "Result not found"})
                    return self.reply(200, file.read_bytes(), "text/csv; charset=utf-8" if filename.endswith("csv") else "application/json; charset=utf-8", filename.endswith("csv"))
                assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                          "/m04.js": "m04.js", "/m04.css": "m04.css",
                          "/developer/integration-api": "integration-sandbox.html",
                          "/developer/integration-api/": "integration-sandbox.html",
                          "/integration-sandbox.js": "integration-sandbox.js",
                          "/integration-sandbox.css": "integration-sandbox.css",
                          "/integration-samples.json": "integration-samples.json"}
                if re.fullmatch(r"/metrics/m0[1-7]/?", path):
                    file = service.root / "frontend/index.html"
                elif path in assets:
                    file = service.root / "frontend" / assets[path]
                else:
                    return self.reply(404, {"error": "Not found"})
                return self.reply(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
            except EvaluationError as exc:
                return self.reply(500, {"status": exc.status, "error": str(exc)})
            except OSError as exc:
                return self.reply(500, {"error": str(exc)})

        def do_POST(self):
            if not self.trusted_request():
                return self.reply(403, {"error": "Local same-origin access required"})
            m04_path = urlparse(self.path).path
            if m04_path == '/api/development/m03/connection':
                from .m03_setup import save_connection
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    require(0 < length <= 131072 and not self.headers.get('Transfer-Encoding'), 'M03 연결 설정은 최대 128 KiB입니다.')
                    require(self.headers.get('Content-Type', '').split(';', 1)[0].strip() == 'application/json', 'Content-Type application/json required')
                    payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
                    with service.lock:
                        result = save_connection(service.root, service.config(), payload)
                    return self.reply(201, result)
                except (ValueError, UnicodeError):
                    return self.reply(400, {'status': 'ERROR', 'error': 'Invalid JSON or Content-Length'})
                except EvaluationError as exc:
                    return self.reply(409 if exc.status == 'RUNNING' else 422, {'status': exc.status, 'error': str(exc)})
                except OSError:
                    return self.reply(500, {'status': 'ERROR', 'error': 'M03 연결 설정을 저장할 수 없습니다.'})
            m03_delete = re.fullmatch(r'/api/development/m03/runs/(DEV-M03-\d{8}T\d{6}-[a-f0-9]{12})/scenarios/delete', m04_path)
            if m03_delete:
                from .m03_management import delete_scenario
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    require(0 < length <= 16384 and not self.headers.get('Transfer-Encoding'), 'M03 JSON 요청은 최대 16 KiB입니다.')
                    require(self.headers.get('Content-Type', '').split(';', 1)[0].strip() == 'application/json', 'Content-Type application/json required')
                    payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
                    with service.lock:
                        result = delete_scenario(service.root, m03_delete[1], payload, session=service.session)
                    return self.reply(200, result)
                except (ValueError, UnicodeError):
                    return self.reply(400, {'status': 'ERROR', 'error': 'Invalid JSON or Content-Length'})
                except EvaluationError as exc:
                    return self.reply(404 if exc.status == 'NOT_FOUND' else 422,
                                      {'status': exc.status, 'error': str(exc)})
                except OSError:
                    return self.reply(500, {'status': 'ERROR', 'error': 'M03 삭제 상태를 저장할 수 없습니다.'})
            if m04_path.startswith('/api/development/m04/'):
                try:
                    require(self.headers.get('Content-Type', '').split(';', 1)[0].strip() == 'application/json', 'Content-Type application/json required')
                    length = int(self.headers.get('Content-Length', '0'))
                    require(0 < length <= 1048576 and not self.headers.get('Transfer-Encoding'), 'JSON body required; maximum 1 MiB')
                    payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
                    manager = service.m04()
                    if m04_path == '/api/development/m04/scripts':
                        return self.reply(201, manager.register(payload))
                    if m04_path == '/api/development/m04/executions':
                        return self.reply(202, manager.create(payload))
                    cancel = re.fullmatch(r'/api/development/m04/executions/(M04-RUN-[0-9a-f]{32})/cancel', m04_path)
                    if cancel:
                        require(isinstance(payload, dict) and not payload, 'Cancel takes an empty JSON object')
                        return self.reply(200, manager.cancel(cancel[1]))
                    return self.reply(404, {'status': 'NOT_FOUND', 'error': 'M04 경로를 찾을 수 없습니다.'})
                except (ValueError, UnicodeError):
                    return self.reply(400, {'status': 'ERROR', 'error': 'Invalid JSON or Content-Length'})
                except EvaluationError as exc:
                    return self.reply(404 if exc.status == 'NOT_FOUND' else 409 if exc.status in {'RUNNING', 'DUPLICATE_EXECUTION'} else 422,
                                      {'status': exc.status, 'error': str(exc)})
                except OSError:
                    return self.reply(500, {'status': 'ERROR', 'error': 'M04 실행 파일과 기록을 저장할 수 없습니다.'})
            comparison_path = urlparse(self.path).path
            if comparison_path in {"/api/development/m01/ground-truths", "/api/development/m01/compare"}:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    maximum = MAX_JSON_BYTES if comparison_path.endswith("ground-truths") else 16384
                    require(0 < length <= maximum and not self.headers.get("Transfer-Encoding"),
                            "A JSON body within the upload limit is required")
                    require(self.headers.get("Content-Type", "").split(";", 1)[0].strip() == "application/json",
                            "Content-Type application/json required")
                    payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
                    with service.lock:
                        store = M01ComparisonStore(service.root, session=service.session)
                        result = (store.upload_truth(payload) if comparison_path.endswith("ground-truths")
                                  else store.compare(payload, service.config()))
                    return self.reply(201, result)
                except (ValueError, UnicodeError):
                    return self.reply(400, {"status": "ERROR", "error": "Invalid JSON or Content-Length"})
                except EvaluationError as exc:
                    return self.reply(404 if exc.status == "NOT_FOUND" else 422,
                                      {"status": exc.status, "error": str(exc)})
                except OSError:
                    return self.reply(500, {"status": "ERROR", "error": "Unable to persist development comparison evidence"})
            if urlparse(self.path).path == "/api/development/m01/csv":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    require(0 < length <= MAX_JSON_BYTES and not self.headers.get("Transfer-Encoding"),
                            "JSON body required; maximum 16 MiB (CSV maximum 10 MiB)")
                    require(self.headers.get("Content-Type", "").split(";", 1)[0].strip() == "application/json",
                            "Content-Type application/json required")
                    payload = json.loads(self.rfile.read(length))
                    with service.lock:
                        result = M01CsvStore(service.root, session=service.session).upload(payload, service.config())
                    return self.reply(201, result)
                except (ValueError, UnicodeError):
                    return self.reply(400, {"status": "ERROR", "error": "Invalid JSON or Content-Length"})
                except EvaluationError as exc:
                    return self.reply(422, {"status": exc.status, "error": str(exc)})
                except OSError:
                    return self.reply(500, {"status": "ERROR", "error": "Unable to persist development CSV evidence"})
            integration = re.fullmatch(r"/api/integrations/(m01|m03|m04|m07)/result", urlparse(self.path).path)
            generation = urlparse(self.path).path == '/api/m03/generate'
            if integration or generation:
                try:
                    require(not generation or not self.headers.get('X-KTL-M03-Adapter'), 'M03 HTTP 생성기를 이 서버의 생성 경로로 다시 연결할 수 없습니다.')
                    length=int(self.headers.get('Content-Length','0'))
                    require(0<length<=1048576 and not self.headers.get('Transfer-Encoding'),'JSON body required; maximum 1 MiB')
                    payload=json.loads(self.rfile.read(length),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
                    if generation:
                        from .m03_integration import generate
                        return self.reply(200,generate(service.root,service.config(),payload))
                    return self.reply(201,service.ingest(integration[1].upper(),payload))
                except (ValueError,UnicodeError):
                    return self.reply(400,{'status':'ERROR','error':'Invalid JSON or Content-Length'})
                except EvaluationError as exc:
                    return self.reply(409 if exc.status=='DUPLICATE_EXTERNAL_RUN' else 503 if generation and exc.status=='NOT_CONFIGURED' else 422,{'status':exc.status,'error':str(exc)})
                except OSError:
                    return self.reply(500,{'status':'ERROR','error':'Unable to persist external evidence'})
            match = re.fullmatch(r"/api/evaluations/(m0[1-7])/run", urlparse(self.path).path)
            if not match:
                return self.reply(404, {"error": "Not found"})
            # Only server-side datasets/configuration; API accepts no paths or commands.
            if self.headers.get("Content-Length", "0") != "0" or self.headers.get("Transfer-Encoding"):
                return self.reply(400, {"error": "This endpoint takes no request body"})
            try:
                result = service.run(match[1].upper(), parse_qs(urlparse(self.path).query).get("mode", ["REFERENCE"])[0])
                code = 422 if result["status"] == "ERROR" else 200
                self.reply(code, result)
            except EvaluationError as exc:
                self.reply(409 if exc.status == "RUNNING" else 422, {"status": exc.status, "error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Unable to persist evaluation evidence"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local KTL evaluation server")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = LocalHTTPServer(("127.0.0.1", args.port), make_handler(Service(session_scoped=True)))
    print(f"Rainbow KTL: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
