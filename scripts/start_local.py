"""Start the checked-out KTL server without machine-specific interpreter paths."""
import argparse
import errno
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def project_root():
    return Path(__file__).resolve().parents[1]


def configure_environment(root):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    executable_directory = str(Path(sys.executable).resolve().parent)
    existing_path = os.environ.get('PATH', '')
    os.environ['PATH'] = executable_directory + (os.pathsep + existing_path if existing_path else '')
    # The existing loader accepts exactly these two test-login names, never a
    # general dotenv file or executable shell content. Existing environment wins.
    from backend.m04.runner import load_login_settings
    load_login_settings(root / '.env.local')
    return root


def serve(root, port):
    from backend.server import main
    main(['--root', str(root), '--port', str(port)])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the local KTL web application')
    parser.add_argument('--port', type=int, default=8000, help='Local port; 0 selects a free port')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    try:
        root = configure_environment(project_root())
        os.chdir(root)
        serve(root, args.port)
    except UnicodeError:
        print('로컬 환경 설정을 읽지 못했습니다. .env.local의 UTF-8 인코딩을 확인하세요.', file=sys.stderr)
        return 1
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE or getattr(exc, 'winerror', None) in {10048, 10013}:
            print(f'127.0.0.1:{args.port} 포트를 사용할 수 없습니다. 기존 서버를 확인하거나 --port로 다른 포트를 지정하세요.', file=sys.stderr)
        else:
            print('KTL 서버를 시작하지 못했습니다. 설치 환경과 프로젝트 파일을 확인하세요.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
