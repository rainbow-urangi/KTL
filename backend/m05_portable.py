"""DEVELOPMENT path/runtime transport around unchanged frozen M05 source bytes."""
import builtins
import copy
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import types

from .evaluators import EvaluationError, require
from .m05_heldout import validate_engine
from .paths import repository_path

VERSIONS = {
    'existing-dataset-cleaning-event-adapter-v1': 'm05_baseline_adapter',
    'session-context-cleaning-v2': 'm05_session_cleaning',
}


RUNTIME_ROOT = pathlib.Path('data/development/m05_portable_runtime')
RUNTIME_MANIFEST = 'runtime_manifest.json'


def _source_root(root):
    root = pathlib.Path(root).resolve()
    if root.name == RUNTIME_ROOT.name and (root/RUNTIME_MANIFEST).is_file():
        host = root.parents[2]
        require((host/RUNTIME_ROOT).resolve() == root, 'M05_RUNTIME_ARCHIVE_LOCATION_INVALID')
        return host
    return root


def runtime_root(root):
    """Read the explicitly restored frozen copy; never stage or mutate on GET."""
    host = pathlib.Path(root).resolve()
    directory = host/RUNTIME_ROOT
    manifest_path = directory/RUNTIME_MANIFEST
    require(manifest_path.is_file(), 'M05_RUNTIME_ARCHIVE_MISSING')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(isinstance(manifest, dict)
            and manifest.get('schema_version') == 'm05-frozen-runtime-copy-v1'
            and manifest.get('run_mode') == 'DEVELOPMENT'
            and manifest.get('official_pass') is None,
            'M05_RUNTIME_ARCHIVE_SCHEMA_INVALID')
    files = manifest.get('files')
    require(isinstance(files, dict) and 1 <= len(files) <= 300,
            'M05_RUNTIME_ARCHIVE_FILES_INVALID')
    for name, expected in files.items():
        path = repository_path(directory, name)
        require(not pathlib.PureWindowsPath(name).is_absolute()
                and not pathlib.PurePosixPath(name).is_absolute()
                and path.is_file() and _sha(path) == expected,
                'M05_RUNTIME_ARCHIVE_CHANGED: '+name)
    for name in ('backend/m05_portable.py', 'backend/paths.py'):
        require(_sha(host/name) == files.get(name), 'M05_RUNTIME_TRANSPORT_CHANGED: '+name)
    originals = manifest.get('host_input_originals')
    require(isinstance(originals, dict), 'M05_RUNTIME_SOURCE_BINDING_MISSING')
    for name, expected in originals.items():
        path = repository_path(host, name)
        require(path.is_file() and _sha(path) == expected,
                'M05_RUNTIME_HOST_INPUT_CHANGED: '+name)
    return directory


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(root, value):
    text = str(value).replace('\\', '/')
    if '/AI-model/' in text:
        host = _source_root(root)
        settings = host/'backend/runtime_paths.json'
        config = json.loads(settings.read_text(encoding='utf-8')) if settings.is_file() else {}
        base = (host/config.get('ai_model_root', '../AI-model')).resolve()
        path = (base/text.split('/AI-model/', 1)[1]).resolve()
        require(path.is_relative_to(base), 'M05_EXTERNAL_PATH_OUTSIDE_CONFIGURED_ROOT')
        if not path.is_file() and text.endswith('/AI-model/dataset.py'):
            path = root/'evaluation_contracts/development/m05_baseline_adapter_candidate/dataset_original.py'
        require(path.is_file(), 'M05_EXTERNAL_SOURCE_MISSING: '+str(path))
        return str(path)
    if '/RainbowKTL/' in text:
        return str(repository_path(root, text))
    return value


def _local_config(root, config, run_mode='DEVELOPMENT'):
    require(run_mode == config.get('run_mode', 'DEVELOPMENT') == 'DEVELOPMENT',
            'M05_PORTABLE_RUNTIME_DEVELOPMENT_ONLY')
    module = VERSIONS.get(config.get('cleaning_model_version'))
    require(module is not None, 'M05_PORTABLE_ENGINE_VERSION_UNSUPPORTED')
    declared = [config[k]['path'] for k in ('interpreter_artifact', 'adapter_artifact')]
    declared += ['--model', config['model_artifact']['path']]
    require(config.get('adapters', {}).get('cleaning') == declared,
            'Engine argv must bind hashed interpreter, adapter and model')
    local = copy.deepcopy(config)
    for key in ('model_artifact', 'adapter_artifact'):
        local[key]['path'] = str(repository_path(root, config[key]['path']))
    require(pathlib.Path(local['adapter_artifact']['path']) == root/'backend'/(module+'.py'),
            'M05_PORTABLE_ENTRYPOINT_MISMATCH')
    interpreter = pathlib.Path(sys.executable).resolve()
    local['interpreter_artifact'] = dict(path=str(interpreter), sha256=_sha(interpreter))
    local['adapters']['cleaning'] = [str(interpreter), local['adapter_artifact']['path'],
                                   '--model', local['model_artifact']['path']]
    validate_engine(root, local)
    return local


def runtime_provenance(root, config, run_mode='DEVELOPMENT'):
    root = pathlib.Path(root).resolve()
    local = _local_config(root, config, run_mode)
    archive_manifest = root/RUNTIME_MANIFEST
    return dict(runtime_root=str(root),
                archive_manifest_sha256=_sha(archive_manifest) if archive_manifest.is_file() else None,
                run_mode='DEVELOPMENT', official_pass=None,
                transport='m05-portable-path-runtime-v1',
                original_interpreter_artifact=copy.deepcopy(config['interpreter_artifact']),
                local_interpreter_artifact=local['interpreter_artifact'],
                transport_sha256={name: _sha(root/name) for name in (
                    'backend/m05_portable.py', 'backend/paths.py',
                    'backend/m05_full_context.py', 'backend/m05_development_contract.py')},
                python_version=platform.python_version(), platform=platform.platform(),
                historical_interpreter_reproduced=(config['interpreter_artifact']['sha256'] == local['interpreter_artifact']['sha256']))


def _loader(root):
    """Private imports/path views; sys.modules and original modules stay untouched."""
    root = pathlib.Path(root).resolve()
    native = type(pathlib.Path())

    class ScopedPath(native):
        def __new__(cls, *parts):
            return super().__new__(cls, *(_resolve(root, p) for p in parts))

        def __init__(self, *parts):
            if native.__init__ is not object.__init__:
                super().__init__(*(_resolve(root, p) for p in parts))

        def __truediv__(self, other):
            return super().__truediv__(_resolve(root, other))

        def __str__(self):
            return super().__str__().replace('\\', '/')

        def read_text(self, encoding=None, errors=None):
            return super().read_text(encoding=encoding or 'utf-8', errors=errors)

    modules = {}
    path_module = types.ModuleType('pathlib')
    path_module.__dict__.update(vars(pathlib)); path_module.Path = ScopedPath
    sys_module = types.ModuleType('sys')
    sys_module.__dict__.update(vars(sys)); sys_module.path = list(sys.path)

    def scoped_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'pathlib':
            return path_module
        if name == 'sys':
            return sys_module
        short = name.removeprefix('backend.')
        if short in {'m05_full_context', 'm05_development_contract', 'm05_session_candidate',
                     'm05_session_cleaning', 'm05_baseline_adapter'}:
            return load(short)
        if level == 1 and not name and 'm05_full_context' in fromlist:
            return types.SimpleNamespace(m05_full_context=load('m05_full_context'))
        return builtins.__import__(name, globals, locals, fromlist, level)

    def load(name):
        if name not in modules:
            path = root/'backend'/(name+'.py')
            module = types.ModuleType('backend._portable_'+name)
            module.__dict__.update(__file__=str(path), __package__='backend',
                                   __builtins__=dict(vars(builtins), __import__=scoped_import))
            modules[name] = module
            exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
            if name in {'m05_full_context', 'm05_session_candidate'}:
                module.validate_engine = lambda active_root, config: validate_engine(
                    active_root, _local_config(pathlib.Path(active_root).resolve(), config))
        return modules[name]
    return load


def prepare(root, manifest, config):
    root = pathlib.Path(root).resolve()
    runtime = runtime_provenance(root, config)
    candidate = _loader(root)('m05_session_candidate')
    prepared = candidate.prepare(root, manifest, config)
    prepared['runtime_provenance'] = runtime
    prepared['binding']['portable_runtime_sha256'] = candidate.fc.digest(runtime)
    prepared['bundle_sha256'] = candidate.fc.digest(prepared['binding'])
    return prepared


def call_adapter(config, name, payload, root, run_mode='DEVELOPMENT'):
    root = pathlib.Path(root).resolve()
    require(name == 'cleaning', 'M05_PORTABLE_CLEANING_ONLY')
    _local_config(root, config, run_mode)
    command = [sys.executable, '-X', 'utf8', '-B', '-m', 'backend.m05_portable', '--root', str(root)]
    try:
        completed = subprocess.run(command, input=json.dumps(dict(config=config, payload=payload), ensure_ascii=False),
            cwd=root, text=True, encoding='utf-8', capture_output=True,
            env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'),
            timeout=config.get('adapter_timeout_seconds', 120), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvaluationError('M05 portable adapter unavailable: '+str(exc), 'ERROR') from exc
    require(completed.returncode == 0,
            'M05 portable adapter exited with code '+str(completed.returncode))
    try:
        response = json.loads(completed.stdout)
    except ValueError as exc:
        raise EvaluationError('M05 portable adapter did not return JSON', 'ERROR') from exc
    require(isinstance(response, dict), 'M05 adapter response must be an object')
    return response


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    root = pathlib.Path(parser.parse_args().root).resolve()
    request = json.load(sys.stdin); config = request['config']; payload = request['payload']
    require(isinstance(payload, dict) and set(payload) == {'events'}, 'Only events allowed')
    local = _local_config(root, config)
    load = _loader(root)
    engine = load(VERSIONS[config['cleaning_model_version']])
    if config['cleaning_model_version'] == 'session-context-cleaning-v2':
        rules_config = json.loads(pathlib.Path(local['model_artifact']['path']).read_text(encoding='utf-8'))
        require(rules_config['rule_version'] == engine.VERSION, 'Version mismatch')
        rules, _ = engine.load_rules(_resolve(root, rules_config['baseline_rules_path']))
    else:
        rules, rules_config = engine.load_rules(local['model_artifact']['path'])
        require(rules_config['rule_version'] == engine.VERSION, 'Version mismatch')
    print(json.dumps(engine.predict(payload['events'], rules), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
