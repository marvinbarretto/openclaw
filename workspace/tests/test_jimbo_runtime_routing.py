"""Tests for Jimbo runtime inbox routing policy."""

import importlib.util
import os
import sys
import unittest


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_routing():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_routing.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_routing_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeRouting(unittest.TestCase):

    def test_build_route_policy_maps_marvin_to_human_required(self):
        runtime_routing = load_runtime_routing()

        policy = runtime_routing.build_route_policy({
            'workflow_hint': 'vault-task-triage',
            'route': {'decision': 'marvin'},
            'delegate': {'agent_type': 'researcher'},
        }, producer='vault-triage')

        self.assertEqual(policy['route'], 'human-required')
        self.assertEqual(policy['execution'], 'record')
        self.assertEqual(policy['status'], 'waiting-human')
        self.assertEqual(policy['capability'], 'researcher')

    def test_build_route_policy_maps_defer_to_nonexecuting_route(self):
        runtime_routing = load_runtime_routing()

        policy = runtime_routing.build_route_policy({
            'workflow_hint': 'dispatch',
            'route': {'decision': 'defer'},
        }, producer='dispatch-proposal')

        self.assertEqual(policy['route'], 'defer')
        self.assertEqual(policy['execution'], 'record')
        self.assertEqual(policy['status'], 'deferred')

    def test_build_route_response_returns_structured_waiting_human_result(self):
        runtime_routing = load_runtime_routing()

        response = runtime_routing.build_route_response({
            'request_id': 'req-1',
            'request': {'command': 'resolve'},
            'route_policy': {
                'route': 'human-required',
                'workflow': 'vault-task-triage',
                'capability': 'researcher',
                'decision': 'marvin',
                'status': 'waiting-human',
                'reason': 'Requires Marvin personally',
            },
        })

        self.assertEqual(response['route'], 'human-required')
        self.assertEqual(response['status'], 'waiting-human')
        self.assertEqual(response['result']['capability'], 'researcher')


if __name__ == '__main__':
    unittest.main()
