"""Verify deployment wiring without loading models or contacting Speakeasy."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
CHATBOT = ROOT / 'additional_files/src/chatbot'
sys.path.insert(0, str(CHATBOT))
spec = importlib.util.spec_from_file_location('speakeasy_entrypoint', CHATBOT / 'main.py')
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class SpeakeasyEntrypointTests(unittest.TestCase):
    def test_default_launch_uses_benchmarked_agent_and_logs_in_before_polling(self):
        graph = ROOT / 'additional_files/data/graph.nt'
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(entrypoint, 'choose_graph_path', return_value=graph), \
             patch.object(entrypoint, 'MovieAgent') as factory, \
             patch.object(entrypoint, 'SpeakeasyClient') as client_factory, \
             redirect_stdout(io.StringIO()):
            entrypoint.main()
            factory.assert_called_once_with(graph, model_name='Qwen/Qwen3.5-4B')
            client_factory.assert_called_once_with(base_url='https://speakeasy.ifi.uzh.ch')
            self.assertEqual(client_factory.return_value.method_calls,
                             [unittest.mock.call.login(), unittest.mock.call.run(factory.return_value)])
            self.assertEqual(os.environ['MESSAGE_TIMEOUT_SECONDS'], '90')

    def test_graph_model_url_and_timeout_overrides_are_retained(self):
        config = {'KNOWLEDGE_GRAPH_PATH': '/tmp/custom-movie-graph.nt',
                  'MOVIE_LLM_MODEL': '/tmp/custom-model',
                  'SPEAKEASY_BASE_URL': 'https://example.invalid',
                  'MESSAGE_TIMEOUT_SECONDS': '45'}
        with patch.dict(os.environ, config, clear=True), \
             patch.object(entrypoint, 'MovieAgent') as factory, \
             patch.object(entrypoint, 'SpeakeasyClient') as client_factory, \
             redirect_stdout(io.StringIO()):
            entrypoint.main()
            factory.assert_called_once_with(Path(config['KNOWLEDGE_GRAPH_PATH']),
                                            model_name=config['MOVIE_LLM_MODEL'])
            client_factory.assert_called_once_with(base_url=config['SPEAKEASY_BASE_URL'])
            self.assertEqual(os.environ['MESSAGE_TIMEOUT_SECONDS'], '45')

    def test_root_main_provides_configured_credentials_and_invokes_entrypoint(self):
        observed = {}
        fake_main = types.ModuleType('main')
        fake_main.main = Mock(side_effect=lambda: observed.update(
            username_present=bool(os.environ.get('SPEAKEASY_USERNAME')),
            password_present=bool(os.environ.get('SPEAKEASY_PASSWORD'))))
        # Execute the real root launcher, but replace its imported entrypoint.
        # No model is constructed and no real login or message can be sent.
        with patch.dict(os.environ, {}, clear=True), \
             patch.dict(sys.modules, {'main': fake_main}), \
             patch.object(sys, 'path', list(sys.path)), \
             redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')
        fake_main.main.assert_called_once_with()
        self.assertEqual(observed, {'username_present': True, 'password_present': True})


if __name__ == '__main__':
    unittest.main()
