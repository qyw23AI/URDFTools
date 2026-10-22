import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from urdftools.agent.providers import CodexCliProvider, LocalHttpProvider, ProviderError, _safe_environment


class ProviderTests(unittest.TestCase):
    def test_local_adapter_rejects_remote_endpoint(self):
        for endpoint in ('https://127.0.0.1/api/generate',
                         'http://example.com/api/generate',
                         'http://127.0.0.1/other',
                         'http://127.0.0.1/api/generate?target=remote'):
            with self.assertRaises(ProviderError):
                LocalHttpProvider(endpoint, 'local-model')

    def test_local_adapter_round_trip(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body['model'] == 'test-model'
                assert 'expected_revision' in body['prompt']
                suggestion = {'schema_version': 1, 'action': 'replace_recipe',
                              'expected_revision': 1, 'recipe': {'schema_version': 1, 'parts': []},
                              'rationale': 'Retain current geometry.'}
                response = json.dumps({'response': json.dumps(suggestion)}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = LocalHttpProvider(f'http://127.0.0.1:{server.server_port}/api/generate', 'test-model')
            self.assertEqual(provider.suggest({'schema_version': 1, 'parts': []}, 1, 'Keep the model')['action'], 'replace_recipe')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_environment_excludes_paid_credentials(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'secret', 'CODEX_API_KEY': 'secret',
                                      'AZURE_OPENAI_KEY': 'secret', 'PATH': '/bin'}):
            env = _safe_environment()
        self.assertEqual(env['PATH'], '/bin')
        self.assertFalse(any('secret' == value for value in env.values()))

    def test_fake_cli_failure_and_response_paths(self):
        recipe = {'schema_version': 1, 'parts': []}
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'fake.py'
            fake.write_text('''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:3] == ['login', 'status']:
    print('Logged in using ChatGPT'); sys.exit(0)
if os.environ.get('FAKE_MODE') == 'failure':
    print('network unavailable', file=sys.stderr); sys.exit(2)
answer = sys.argv[sys.argv.index('--output-last-message')+1]
payload = {'schema_version':1,'action':'replace_recipe','expected_revision':1,
           'recipe':{'schema_version':1,'parts':[]},'rationale':'No geometry change.'}
open(answer,'w').write(json.dumps(payload if os.environ.get('FAKE_MODE') != 'invalid' else {'shell':'bad'}))
print(json.dumps({'type':'turn.completed'}))
''')
            fake.chmod(0o755)
            provider = CodexCliProvider(str(fake), timeout=5)
            with patch.dict('os.environ', {'FAKE_MODE': 'failure'}):
                with self.assertRaisesRegex(ProviderError, 'transport or model'):
                    provider.suggest(recipe, 1, 'Make a suggestion')
            with patch.dict('os.environ', {'FAKE_MODE': 'invalid'}):
                with self.assertRaisesRegex(ProviderError, 'invalid suggestion'):
                    provider.suggest(recipe, 1, 'Make a suggestion')
            with patch.dict('os.environ', {'FAKE_MODE': 'success'}):
                self.assertEqual(provider.suggest(recipe, 1, 'Make a suggestion')['action'], 'replace_recipe')


if __name__ == '__main__':
    unittest.main()
