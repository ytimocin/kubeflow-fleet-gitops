"""Check completion gates: placement availability must never imply training success."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('runner', Path(__file__).parents[1] / 'scripts/remote-training.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

JOB = {'metadata': {}, 'spec': {}}
PLACEMENT = {'metadata': {}, 'spec': {'resourceSelectors': [{}]}}


def scheduled(generation=2, observed=2, clusters=('west',)):
    return {'metadata': {'generation': generation}, 'status': {
        'conditions': [{'type': 'ResourcePlacementScheduled', 'status': 'True', 'observedGeneration': observed}],
        'placementStatuses': [{'clusterName': c, 'conditions': [{'type': 'Scheduled', 'status': 'True'}]} for c in clusters]}}


class CompletionGateTests(unittest.TestCase):
    def execute(self, member, placement=None, ticks=None):
        hub = Mock()
        hub.request.side_effect = [None, {}, None, {}, placement or scheduled()]
        return runner.run(hub, {'west': member}, JOB, PLACEMENT, 'run-1', timeout=10,
                          clock=Mock(side_effect=ticks or [0, 1]), sleep=Mock())

    def remote(self, state):
        name, job, _ = runner.prepare(JOB, PLACEMENT, 'run-1')
        job['status'] = {'conditions': [{'type': state, 'status': 'True'}]}
        return name, job

    def test_stale_generation_is_not_selected(self):
        self.assertIsNone(runner.selected_member(scheduled(observed=1)))

    def test_multiple_selected_members_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            runner.selected_member(scheduled(clusters=('east', 'west')))

    def test_available_placement_does_not_finish_pending_training(self):
        _, job = self.remote('Running')
        member = Mock(); member.request.return_value = job
        with self.assertRaises(TimeoutError):
            self.execute(member, ticks=[0, 1, 11])

    def test_failed_training_fails_pipeline(self):
        _, job = self.remote('Failed')
        member = Mock(); member.request.return_value = job
        with self.assertRaisesRegex(RuntimeError, 'Training failed'):
            self.execute(member)

    def test_missing_member_connection_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, 'No read connection'):
            self.execute(Mock(), placement=scheduled(clusters=('east',)))

    def test_success_requires_cuda_evidence(self):
        name, job = self.remote('Succeeded')
        member = Mock(); member.request.side_effect = [job, {'items': [{'metadata': {'name': name + '-master-0'}}]}, 'CPU training succeeded']
        with self.assertRaisesRegex(RuntimeError, 'CUDA evidence'):
            self.execute(member)

    def test_success_returns_actual_selected_member(self):
        name, job = self.remote('Succeeded')
        member = Mock(); member.request.side_effect = [job, {'items': [{'metadata': {'name': name + '-master-0'}}]}, 'GPU=Tesla T4 CUDA=12.4\nTRAINING_SUCCEEDED device=cuda']
        self.assertEqual(self.execute(member)['cluster'], 'west')

    def test_existing_foreign_job_is_not_reused(self):
        _, job, _ = runner.prepare(JOB, PLACEMENT, 'run-1')
        api = Mock(); api.request.return_value = {'metadata': {'labels': {runner.RUN_LABEL: 'other'}}}
        with self.assertRaisesRegex(RuntimeError, 'different run'):
            runner.create_once(api, runner.JOB_PATH, job)
        self.assertEqual(api.request.call_count, 1)

    def test_unresolved_run_id_is_rejected(self):
        with self.assertRaises(ValueError):
            runner.prepare(JOB, PLACEMENT, '{{$.pipeline_job_uuid}}')


if __name__ == '__main__':
    unittest.main()
