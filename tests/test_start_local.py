"""Portable launcher checks without starting a server, browser or provider."""
from contextlib import redirect_stderr, redirect_stdout
import errno
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/start_local.py'
_SPEC = importlib.util.spec_from_file_location('ktl_start_local', _SCRIPT)
launcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launcher)


class StartLocalTests(unittest.TestCase):
    def test_root_is_resolved_from_launcher_not_working_directory(self):
        with mock.patch('os.getcwd', return_value='unrelated working directory'):
            self.assertEqual(launcher.project_root(), _SCRIPT.parents[1])

    def test_spaces_same_python_path_only_two_credentials_and_no_config_write(self):
        with tempfile.TemporaryDirectory(prefix='KTL home path with spaces ') as temporary:
            root = Path(temporary)
            (root / 'backend').mkdir()
            config = root / 'backend/config.json'
            config.write_text('{"adapters":{"scenario_generation":["python"]}}', encoding='utf-8')
            before = config.read_bytes()
            (root / '.env.local').write_text(
                'KTL_M04_RBEM_USERNAME=synthetic-file-user\n'
                'KTL_M04_RBEM_PASSWORD="synthetic-file-password"\n'
                'KTL_M07_OPENAI_API_KEY=synthetic-provider-key\n'
                'UNRELATED_SETTING=must-not-load\n', encoding='utf-8')
            executable = root / 'venv with spaces' / 'python.exe'
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, 'executable', str(executable)), mock.patch.object(sys, 'path', list(sys.path)), \
                 mock.patch.dict(os.environ, {'PATH': 'existing-search-path', 'KTL_M04_RBEM_USERNAME': 'synthetic-process-user'}, clear=True), \
                 redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(launcher.configure_environment(root), root.resolve())
                self.assertEqual(os.environ['PATH'].split(os.pathsep)[0], str(executable.parent.resolve()))
                self.assertTrue(os.environ['PATH'].endswith('existing-search-path'))
                self.assertEqual(os.environ['KTL_M04_RBEM_USERNAME'], 'synthetic-process-user')
                self.assertEqual(os.environ['KTL_M04_RBEM_PASSWORD'], 'synthetic-file-password')
                self.assertNotIn('KTL_M07_OPENAI_API_KEY', os.environ)
                self.assertNotIn('UNRELATED_SETTING', os.environ)
                self.assertEqual(sys.path[0], str(root.resolve()))
            self.assertEqual(out.getvalue() + err.getvalue(), '')
            self.assertEqual(config.read_bytes(), before)

    def test_port_zero_and_absolute_root_are_forwarded_without_feature_execution(self):
        root = Path(tempfile.gettempdir()) / 'synthetic KTL clone'
        with mock.patch.object(launcher, 'project_root', return_value=root), \
             mock.patch.object(launcher, 'configure_environment', return_value=root) as configure, \
             mock.patch.object(launcher.os, 'chdir') as chdir, mock.patch.object(launcher, 'serve') as serve:
            self.assertEqual(launcher.main(['--port', '0']), 0)
            configure.assert_called_once_with(root)
            chdir.assert_called_once_with(root)
            serve.assert_called_once_with(root, 0)

    def test_existing_port_has_actionable_message_without_exception_or_secret_output(self):
        root = _SCRIPT.parents[1]
        for windows in (False, True):
            error = OSError(errno.EADDRINUSE if not windows else errno.EACCES, 'synthetic-secret-in-error')
            if windows:
                error.winerror = 10048
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(launcher, 'configure_environment', return_value=root), \
                 mock.patch.object(launcher.os, 'chdir'), mock.patch.object(launcher, 'serve', side_effect=error), \
                 redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(launcher.main(['--port', '8001']), 1)
            self.assertIn('8001', err.getvalue())
            self.assertIn('--port', err.getvalue())
            self.assertNotIn('synthetic-secret-in-error', out.getvalue() + err.getvalue())

    def test_port_bounds_reject_before_starting_or_loading_credentials(self):
        with mock.patch.object(launcher, 'configure_environment') as configure, redirect_stderr(io.StringIO()):
            for port in ('-1', '65536'):
                with self.assertRaises(SystemExit) as caught:
                    launcher.main(['--port', port])
                self.assertEqual(caught.exception.code, 2)
            configure.assert_not_called()

    def test_invalid_private_settings_do_not_print_decoder_payload(self):
        error = UnicodeDecodeError('utf8', b'synthetic-private-setting-\xff', 26, 27, 'invalid')
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(launcher, 'configure_environment', side_effect=error), \
             mock.patch.object(launcher, 'serve') as serve, redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(launcher.main([]), 1)
            serve.assert_not_called()
        self.assertNotIn('synthetic-private-setting', out.getvalue() + err.getvalue())
        self.assertIn('UTF-8', err.getvalue())


if __name__ == '__main__':
    unittest.main()
