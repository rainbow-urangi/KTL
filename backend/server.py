"""Local KTL evaluation service. Run: python3 -m backend.server"""
import argparse
import json
import math
import mimetypes
import re
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .evaluators import (METRICS, REFERENCE, EvaluationError, M02Evaluator, M05Evaluator, M06Evaluator, csv_evidence, read_json, require, call_adapter)
from .registry import MODES, VERSION, EXTERNAL
from .run_storage import save_run
from .integration_store import ingest
from .data_sources import V62ReferenceProvider, OfficialEvaluationDataSource
from .contracts import cleaning_payload
from .m01 import M01CsvStore, M01ComparisonStore, MAX_JSON_BYTES

ROOT = Path(__file__).resolve().parents[1]


class Service:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.lock = threading.Lock()

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
        return config

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
            latest_path = self.root / "results" / mode.lower() / ("latest-" + key + ".json")
            latest = read_json(latest_path) if latest_path.exists() else None
            if key in EXTERNAL and latest and latest.get('status') == 'COMPLETED':
                prepared.update(status='COMPLETED',details={'external_result_received':True})
            result.append({"metric_id": key, "metric_name": name, "dataset": source.dataset_id,
                           "expected_sample_count": count, "target": config["targets"].get(key),
                           "operator": operator, "latest": latest, "status": prepared["status"],
                           "details": prepared["details"], "error": prepared.get("error")})
        return {"run_mode": mode, "metrics": result, "model": {"version": "V6.2", "frozen": True, "reference_counts": REFERENCE}}

    def ingest(self, metric, payload):
        require(metric in EXTERNAL, 'Unsupported integration metric')
        with self.lock:
            return ingest(self.root, self.config(), metric, payload)

    def run(self, metric, mode="REFERENCE"):
        require(mode in MODES and metric in METRICS, "Invalid mode or metric")
        if not self.lock.acquire(blocking=False):
            raise EvaluationError("An evaluation is already running", "RUNNING")
        try:
            config = self.config(); source = self.source(mode, config)
            if metric in EXTERNAL:
                latest=self.root/'results'/mode.lower()/('latest-'+metric+'.json')
                if latest.exists() and read_json(latest).get('status')=='COMPLETED':
                    return read_json(latest)
            if mode == 'DEVELOPMENT':
                if metric in {'M02','M06'}:
                    from .model_runner import EvaluationModelRunner
                    from .model_runner.evaluation import evaluate_run
                    return evaluate_run(self.root,config,EvaluationModelRunner(self.root).run())[metric]
                prepared=self.prepare(source,metric)
                return save_run(self.root,metric,mode,config,{'status':prepared['status'],'score':None,'sample_count':None,
                    'dataset_id':source.dataset_id,'source_type':'DEVELOPMENT','details':prepared['details']},[])
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
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="evidence.csv"')
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
                    return self.reply(200, M01CsvStore(service.root).list())
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
                comparison_match = re.fullmatch(r"/api/development/m01/comparisons/([0-9a-f]{32})(/evidence.csv|/verification)?", path)
                if comparison_match:
                    try:
                        store = M01ComparisonStore(service.root)
                        if comparison_match[2] == "/evidence.csv":
                            return self.reply(200, store.evidence(comparison_match[1]), "text/csv; charset=utf-8", True)
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
                        store = M01CsvStore(service.root)
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
                    file = service.root / "results" / ({"REF":"reference","EVAL":"official","DEV":"development"}[run_id.split("-")[0]]) / run_id / filename
                    if not file.is_file():
                        return self.reply(404, {"error": "Result not found"})
                    return self.reply(200, file.read_bytes(), "text/csv; charset=utf-8" if filename.endswith("csv") else "application/json; charset=utf-8", filename.endswith("csv"))
                assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
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
            except (EvaluationError, OSError) as exc:
                return self.reply(500, {"error": str(exc)})

        def do_POST(self):
            if not self.trusted_request():
                return self.reply(403, {"error": "Local same-origin access required"})
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
                        store = M01ComparisonStore(service.root)
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
                        result = M01CsvStore(service.root).upload(payload, service.config())
                    return self.reply(201, result)
                except (ValueError, UnicodeError):
                    return self.reply(400, {"status": "ERROR", "error": "Invalid JSON or Content-Length"})
                except EvaluationError as exc:
                    return self.reply(422, {"status": exc.status, "error": str(exc)})
                except OSError:
                    return self.reply(500, {"status": "ERROR", "error": "Unable to persist development CSV evidence"})
            integration = re.fullmatch(r"/api/integrations/(m01|m04|m07)/result", urlparse(self.path).path)
            if integration:
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    require(0<length<=1048576 and not self.headers.get('Transfer-Encoding'),'JSON body required; maximum 1 MiB')
                    payload=json.loads(self.rfile.read(length),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
                    return self.reply(201,service.ingest(integration[1].upper(),payload))
                except (ValueError,UnicodeError):
                    return self.reply(400,{'status':'ERROR','error':'Invalid JSON or Content-Length'})
                except EvaluationError as exc:
                    return self.reply(409 if exc.status=='DUPLICATE_EXTERNAL_RUN' else 422,{'status':exc.status,'error':str(exc)})
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
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Service()))
    print(f"Rainbow KTL: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
