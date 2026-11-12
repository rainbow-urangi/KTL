"""Reproduce exact pinned artifact bytes in a new directory, never edit sources."""
import hashlib
import json
from pathlib import Path
from .errors import ValidationError


BASE = Path(__file__).resolve().parents[1]
UPSTREAM = BASE.parent / 'workflow_candidate_v1_2' / 'artifacts'
PINNED = {
    'model.pt': '1832314d23fa44962eb17fc85d5000477476aed7e0508ee9fd8ed93a869f741e',
    'feature_config.json': '3afa6136ea7620fea719be4b35308c6282bb5aa7575b0238c3920bdd6fa307f4',
    'representation_config.json': '4afebc4ff99debf62c6d8d16d830783275d57feed681c2c955cd35c8f0995296',
    'training_manifest.json': '4a60515741c355b7e973c109379090a281447718aa20911f0a088f4640156a91',
    'representation_encoder_config.json': '40bf3ea8701abcbd5ba1ee624d50386788c34062cdf850cba2374d9f3dddf4b3',
    'representation_encoder.pt': '86c77fa404223f97f4cf512244405d199cb7f2f76d2bb05b8886fbcf529eb7cf',
    'model_config.json': 'd9f5903ed26dd5423385b701a3af408257b57e8c3dc543b9111682641edadab1',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def materialize(source, destination, *, expected=None):
    """expected is injectable for temporary unit fixtures; CLI always uses PINNED."""
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    contract = PINNED if expected is None else expected
    if destination.resolve().is_relative_to(source) or destination.exists() or destination.is_symlink():
        raise ValidationError('ARTIFACT_STAGE_NOT_NEW', 'Artifact staging must use a new directory')
    manifest_path = source / 'model_manifest.json'
    if manifest_path.is_symlink():
        raise ValidationError('ARTIFACT_SOURCE_SYMLINK', 'Artifact manifest symlinks are not supported')
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    if manifest.get('artifact_sha256') != contract:
        raise ValidationError('PINNED_MANIFEST_MISMATCH', 'Upstream manifest does not match the pinned artifact contract')
    prepared, proof = {}, []
    for name, pinned in contract.items():
        if Path(name).name != name or len(pinned) != 64:
            raise ValidationError('PINNED_CONTRACT_INVALID', 'Invalid pinned artifact entry')
        path = source / name
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValidationError('ARTIFACT_SOURCE_BOUNDARY', 'Artifact source escapes its registered directory')
        raw = path.read_bytes()
        canonical, method = raw, 'UNCHANGED_ORIGINAL_BYTES'
        if digest(raw) != pinned:
            if path.suffix != '.json':
                raise ValidationError('PINNED_BINARY_HASH_MISMATCH', 'Pinned binary artifact hash mismatch')
            canonical = raw.replace(b'\r\n', b'\n')
            if digest(canonical) != pinned:
                raise ValidationError('PINNED_JSON_HASH_MISMATCH', 'Pinned JSON artifact hash mismatch')
            method = 'EXACT_PINNED_CRLF_TO_LF_REPRODUCTION'
        prepared[name] = canonical
        proof.append(dict(name=name, source_sha256=digest(raw), pinned_sha256=pinned,
                          staged_sha256=digest(canonical), method=method, source_modified=False))
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in prepared.items():
        path = destination / name
        with path.open('xb') as handle:
            handle.write(raw)
        if digest(path.read_bytes()) != contract[name]:
            raise ValidationError('STAGED_ARTIFACT_HASH_MISMATCH', 'Staged artifact verification failed')
    with (destination / 'model_manifest.json').open('xb') as handle:
        handle.write(original_manifest)
    for item in proof:
        if digest((source / item['name']).read_bytes()) != item['source_sha256']:
            raise ValidationError('ARTIFACT_SOURCE_CHANGED', 'Artifact source changed during staging')
    result = dict(source_directory=str(source), staged_directory=str(destination.resolve()),
                  upstream_manifest_sha256=digest(original_manifest),
                  original_manifest_preserved=True, files=proof)
    (destination / 'artifact-reproduction-proof.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
