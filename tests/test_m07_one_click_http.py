"""Loopback HTTP routing only; synthetic inputs and no LLM or browser work."""
from copy import deepcopy
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import Mock

from backend.m07.meeting import prepare_batch
from backend.server import make_handler
from tests.test_m07_meeting_contract import batch


class OneClickHTTPTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        manager = Mock()

        def create(payload, *, auto_validate=False):
            prepare_batch(payload)
            self.calls.append((deepcopy(payload), auto_validate))
            return dict(generation=dict(auto_validate=auto_validate))

        manager.create_meeting.side_effect = create
        manager.current_provider_state.return_value = dict(blocked=False)
        service = Mock(session=None, _m07=manager)
        service.m07.return_value = manager
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def post(self, payload, raw=False):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request('POST', '/api/development/m07/meeting-generations',
                               payload if raw else json.dumps(payload),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_one_click_flag_is_separate_from_unchanged_frozen_inputs(self):
        payload = batch()
        original = deepcopy(payload)
        status, response = self.post(dict(payload, auto_validate=True))
        self.assertEqual(status, 202, response)
        self.assertIs(response['generation']['auto_validate'], True)
        self.assertEqual(self.calls, [(original, True)])
        self.assertEqual(payload, original)

    def test_legacy_request_remains_generation_only(self):
        payload = batch()
        for extra in ({}, dict(auto_validate=False)):
            with self.subTest(extra=extra):
                status, response = self.post(dict(payload, **extra))
                self.assertEqual(status, 202, response)
                self.assertIs(response['generation']['auto_validate'], False)
        self.assertEqual(self.calls, [(payload, False), (payload, False)])

    def test_only_literal_boolean_is_accepted_before_work(self):
        for value in (0, 1, 'true', 'false', None, [], {}):
            with self.subTest(value=value):
                status, response = self.post(dict(batch(), auto_validate=value))
                self.assertEqual(status, 422, response)
        self.assertEqual(self.calls, [])

    def test_duplicate_keys_and_extra_input_fields_do_not_start_work(self):
        raw = json.dumps(batch())[:-1] + ',"auto_validate":true,"auto_validate":false}'
        status, response = self.post(raw, raw=True)
        self.assertEqual(status, 400, response)
        status, response = self.post(dict(batch(), auto_validate=True, score=100))
        self.assertEqual(status, 422, response)
        for payload in (None, [], 'wrong root'):
            status, response = self.post(payload)
            self.assertEqual(status, 422, response)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
