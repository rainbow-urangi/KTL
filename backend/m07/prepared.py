# 등록한 Python 원본 검사
import ast
import base64
import binascii
import hashlib
import io
import os
import re
import tokenize
from pathlib import Path

from ..evaluators import EvaluationError, require


LIMIT = 262144
_AUTH_NAME = re.compile(r'(?:^|_)(?:password|passwd|pwd|secret|token|authorization|cookie|api_key|username|user_name|login_id|비밀번호|아이디)$', re.I)
_IDENTITY_NAME = re.compile(r'(?:^|_)(?:username|user_name|login_id|아이디)$', re.I)


def _tokens(code):
    values = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type not in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}:
                values.append(token)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return values


def _literal(token):
    if token.type != tokenize.STRING:
        return None
    try:
        value = ast.literal_eval(token.string)
        return value if isinstance(value, str) else None
    except (ValueError, SyntaxError):
        return None


def _known_secrets(root):
    values = dict(os.environ)
    path = Path(root) / '.env.local'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, separator, value = line.strip().partition('=')
            if separator and key.strip() not in values:
                values[key.strip()] = value.strip().strip('\"\'')
    return [(value, bool(_IDENTITY_NAME.search(key))) for key, value in values.items()
            if _AUTH_NAME.search(key) and isinstance(value, str) and len(value) >= 4]


def _source(code, identity, known):
    require(not any(secret in code for secret, identity_value in known if not identity_value),
            '코드에 인증정보 원문을 넣을 수 없습니다. 서버 환경변수를 사용하세요.')
    tokens = _tokens(code.lstrip('\ufeff'))
    declarations = []
    for index, token in enumerate(tokens):
        if token.type == tokenize.NAME and token.string == 'SCENARIO_ID':
            if index + 2 < len(tokens) and tokens[index + 1].string == '=':
                require(token.start[1] == 0 and index + 3 < len(tokens)
                        and tokens[index + 3].type in {tokenize.NEWLINE, tokenize.ENDMARKER},
                        'SCENARIO_ID는 모듈 첫 단계에서 문자열 하나로 선언하세요.')
                declarations.append(_literal(tokens[index + 2]))
        value = _literal(token)
        if value is not None:
            require(not any(value == secret if identity_value else secret in value for secret, identity_value in known),
                    '코드에 인증정보 원문을 넣을 수 없습니다. 서버 환경변수를 사용하세요.')
            require(not re.search(r'(?i)\bBearer\s+\S|https?://[^\s/@]+:[^\s/@]+@', value),
                    '코드에 인증정보 또는 인증 URL을 넣을 수 없습니다.')
        name = token.string if token.type == tokenize.NAME else value
        if isinstance(name, str) and _AUTH_NAME.search(name) and index + 2 < len(tokens):
            if tokens[index + 1].string in {'=', ':'}:
                require(not _literal(tokens[index + 2]),
                        '인증값은 코드에 직접 작성하지 말고 서버 환경변수를 사용하세요.')
    require(declarations == [identity], '코드마다 선택한 시나리오와 일치하는 SCENARIO_ID 문자열 선언이 필요합니다.')


def read_codes(root, values, refs):
    require(isinstance(values, list) and 1 <= len(values) <= 20 and len(values) == len(refs),
            '선택한 각 시나리오에 코드 파일을 하나씩 등록하세요.')
    identities = {row['scenario_id'] for row in refs}
    output = {}
    known = _known_secrets(root)
    for row in values:
        require(isinstance(row, dict) and set(row) == {'scenario_id', 'filename', 'code_base64', 'sha256'},
                '코드 파일의 시나리오 ID, 파일명, 원본과 SHA-256이 필요합니다.')
        identity, filename = row['scenario_id'], row['filename']
        require(isinstance(identity, str) and identity in identities and identity not in output,
                '등록 코드와 선택 시나리오를 일대일로 연결하세요.')
        require(isinstance(filename, str) and 1 <= len(filename) <= 120 and filename.lower().endswith('.py')
                and re.fullmatch(r'[^/\\:\x00-\x1f]+', filename) and filename not in {'.py', '..py'},
                'Python 파일명만 사용할 수 있습니다.')
        encoded, checksum = row['code_base64'], row['sha256']
        require(isinstance(encoded, str) and 0 < len(encoded) <= 349528,
                '코드 파일은 256 KiB 이하여야 합니다.')
        require(isinstance(checksum, str) and re.fullmatch(r'[a-f0-9]{64}', checksum), '코드 원본 SHA-256이 필요합니다.')
        try:
            raw = base64.b64decode(encoded, validate=True)
            require(0 < len(raw) <= LIMIT and b'\x00' not in raw, '코드 파일은 256 KiB 이하의 UTF-8이어야 합니다.')
            code = raw.decode('utf-8-sig')
        except (binascii.Error, ValueError, UnicodeError):
            raise EvaluationError('코드 파일은 올바른 base64 및 UTF-8이어야 합니다.') from None
        require(hashlib.sha256(raw).hexdigest() == checksum, '등록한 코드 원본 SHA-256이 일치하지 않습니다.')
        _source(code, identity, known)
        output[identity] = dict(raw=raw, source_filename=filename, source_file_sha256=checksum)
    require(set(output) == identities, '선택한 모든 시나리오의 코드 파일이 필요합니다.')
    return output
