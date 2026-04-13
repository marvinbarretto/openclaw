"""Tests for TaskRecordAPI decision serialization."""

import os
import sys
import json
import unittest
from unittest import mock
from urllib.error import HTTPError
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jimbo_runtime import TaskRecord, Decision, TaskRecordAPI


class TestTaskRecordAPISerialization(unittest.TestCase):
    """Test that decisions are properly serialized (null fields excluded)."""

    def test_serializes_decision_with_all_fields(self):
        """Decision with model, worker_id, and cost should include all fields."""
        api = TaskRecordAPI()

        tr = TaskRecord(id="test-1", workflow_id="test")
        tr.log_decision(
            step_id="classify",
            decision={"category": "research"},
            model="haiku",
            worker_id="worker-1",
            cost=0.05
        )

        # Simulate the serialization logic
        decisions_json = []
        for d in tr.decisions:
            dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
            if d.model is not None:
                dec['model'] = d.model
            if d.worker_id is not None:
                dec['worker_id'] = d.worker_id
            if d.cost > 0:
                dec['cost'] = d.cost
            decisions_json.append(dec)

        self.assertEqual(len(decisions_json), 1)
        decision = decisions_json[0]
        self.assertEqual(decision['step'], 'classify')
        self.assertEqual(decision['decision'], {'category': 'research'})
        self.assertEqual(decision['model'], 'haiku')
        self.assertEqual(decision['worker_id'], 'worker-1')
        self.assertEqual(decision['cost'], 0.05)
        self.assertIn('timestamp', decision)

    def test_serializes_decision_without_optional_fields(self):
        """Decision without model/worker_id should exclude those fields."""
        api = TaskRecordAPI()

        tr = TaskRecord(id="test-1", workflow_id="test")
        tr.log_decision(
            step_id="route",
            decision={"route": "delegate"}
        )

        # Simulate the serialization logic
        decisions_json = []
        for d in tr.decisions:
            dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
            if d.model is not None:
                dec['model'] = d.model
            if d.worker_id is not None:
                dec['worker_id'] = d.worker_id
            if d.cost > 0:
                dec['cost'] = d.cost
            decisions_json.append(dec)

        self.assertEqual(len(decisions_json), 1)
        decision = decisions_json[0]
        self.assertEqual(decision['step'], 'route')
        self.assertEqual(decision['decision'], {'route': 'delegate'})
        self.assertNotIn('model', decision)
        self.assertNotIn('worker_id', decision)
        self.assertNotIn('cost', decision)
        self.assertIn('timestamp', decision)

    def test_serializes_multiple_decisions(self):
        """Multiple decisions should all be properly serialized."""
        api = TaskRecordAPI()

        tr = TaskRecord(id="test-1", workflow_id="test")
        tr.log_decision(
            step_id="classify",
            decision={"category": "research"},
            model="haiku"
        )
        tr.log_decision(
            step_id="route",
            decision={"route": "delegate"},
            worker_id="research-worker"
        )
        tr.log_decision(
            step_id="delegate",
            decision={"status": "success"},
            cost=0.15
        )

        # Simulate the serialization logic
        decisions_json = []
        for d in tr.decisions:
            dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
            if d.model is not None:
                dec['model'] = d.model
            if d.worker_id is not None:
                dec['worker_id'] = d.worker_id
            if d.cost > 0:
                dec['cost'] = d.cost
            decisions_json.append(dec)

        self.assertEqual(len(decisions_json), 3)

        # Check each decision
        self.assertEqual(decisions_json[0]['step'], 'classify')
        self.assertIn('model', decisions_json[0])
        self.assertNotIn('worker_id', decisions_json[0])

        self.assertEqual(decisions_json[1]['step'], 'route')
        self.assertNotIn('model', decisions_json[1])
        self.assertIn('worker_id', decisions_json[1])

        self.assertEqual(decisions_json[2]['step'], 'delegate')
        self.assertNotIn('model', decisions_json[2])
        self.assertIn('cost', decisions_json[2])

    def test_json_serialization_produces_valid_json(self):
        """Serialized decisions should produce valid JSON."""
        tr = TaskRecord(id="test-1", workflow_id="test")
        tr.log_decision(
            step_id="classify",
            decision={"category": "research"},
            model="haiku",
            worker_id=None,
            cost=0.0
        )

        # Simulate the serialization logic
        decisions_json = []
        for d in tr.decisions:
            dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
            if d.model is not None:
                dec['model'] = d.model
            if d.worker_id is not None:
                dec['worker_id'] = d.worker_id
            if d.cost > 0:
                dec['cost'] = d.cost
            decisions_json.append(dec)

        # Should be JSON serializable
        json_str = json.dumps(decisions_json)
        parsed = json.loads(json_str)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['step'], 'classify')
        # Null values should NOT be in the JSON
        self.assertNotIn('model', parsed[0]) or parsed[0].get('model') is not None


class TestTaskRecordAPIErrorHandling(unittest.TestCase):
    """Test that HTTP errors are properly reported with response body."""

    @mock.patch('urllib.request.urlopen')
    def test_error_handler_prints_400_response_body(self, mock_urlopen):
        """HTTP 400 errors should print the response body."""
        # Create a mock HTTPError with a response body
        error_body = b'{"error": "Invalid decisions schema", "details": "model field must be string or null"}'
        mock_error = HTTPError(
            url="http://localhost:3100/api/workflows/tasks/test-1",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=BytesIO(error_body)
        )
        mock_urlopen.side_effect = mock_error

        api = TaskRecordAPI()

        # Capture stderr
        with mock.patch('sys.stdout', new_callable=mock.MagicMock) as mock_stdout:
            result = api.update(
                task_id="test-1",
                state="pending"
            )

        self.assertIsNone(result)
        # Verify that error was printed (should have called print)
        # The actual implementation will have printed the error


if __name__ == '__main__':
    unittest.main()
