"""Artifact integrity, failed quality gates, and Fleet resource boundaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/'src'))
from storage import Store, encode, run_prefix
from tasks import prepare, validate, evaluate, publish
from remote import resources, wait_for_training


class MemoryStore(Store):
    def __init__(self):
        self.data = {}
        self.container = Mock()
        self.container.download_blob.side_effect = lambda name: Mock(readall=lambda: self.data[name])

    def put(self, name, data):
        if name in self.data and self.data[name] != data: raise ValueError('Conflicting artifact')
        self.data[name] = data
        return {'blob': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.run = 'test-run'
        self.prefix = run_prefix(self.run)
        self.dataset = prepare(self.store, self.run)
        self.validated = validate(self.store, self.run, self.dataset)

    def training_result(self, bias=0.3):
        model = self.store.put_json(self.prefix+'training/model.json', {
            'weights': [[(i+1)/8] for i in range(8)], 'bias': bias})
        checkpoint = self.store.put(self.prefix+'training/checkpoint.pt', b'unit-test-checkpoint')
        manifest = self.store.put_json(self.prefix+'training/manifest.json', {
            'run_id': self.run, 'validated_dataset': self.validated, 'model': model,
            'checkpoint': checkpoint, 'gpu': 'test GPU'})
        return {'cluster': 'west', 'job': 'test', 'manifest': manifest}

    def test_success_preserves_dataset_model_and_cluster_provenance(self):
        result = self.training_result()
        metrics = evaluate(self.store, self.run, self.validated, result, .02)
        published = publish(self.store, self.run, metrics)
        summary = self.store.get_json(published, self.prefix)
        self.assertEqual('west', summary['training_cluster'])
        self.assertEqual(self.validated, summary['dataset'])
        self.assertEqual('Published', summary['status'])

    def test_tampered_data_is_rejected(self):
        manifest = self.store.get_json(self.dataset, self.prefix)
        ref = manifest['datasets']['train']
        self.store.data[ref['blob']] = b'corrupt'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate(self.store, self.run, self.dataset)

    def test_cross_run_artifact_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'another run'):
            self.store.get(self.dataset, run_prefix('another-run'))

    def test_quality_failure_writes_metrics_but_cannot_publish(self):
        result = self.training_result(bias=100)
        with self.assertRaisesRegex(ValueError, 'quality gate'):
            evaluate(self.store, self.run, self.validated, result, .02)
        name = self.prefix+'evaluation/metrics.json'
        raw = self.store.data[name]
        ref = {'blob': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        with self.assertRaisesRegex(ValueError, 'passing evaluation'):
            publish(self.store, self.run, ref)
        self.assertNotIn(self.prefix+'published/result.json', self.store.data)

    def test_missing_model_blocks_publication(self):
        result = self.training_result()
        metrics = evaluate(self.store, self.run, self.validated, result, .02)
        del self.store.data[self.prefix+'training/model.json']
        with self.assertRaises(KeyError):
            publish(self.store, self.run, metrics)
        self.assertNotIn(self.prefix+'published/result.json', self.store.data)

    def test_placement_selects_only_its_own_gpu_job(self):
        name, job, rp = resources(self.run, 'west', 'image@sha256:abc', 'account', 'container', self.validated)
        self.assertEqual(name, rp['spec']['resourceSelectors'][0]['name'])
        self.assertEqual(['west'], rp['spec']['policy']['clusterNames'])
        pod = job['spec']['pytorchReplicaSpecs']['Master']['template']
        self.assertEqual('blob-trainer', pod['spec']['serviceAccountName'])
        self.assertEqual(1, pod['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu'])
        self.assertEqual('true', pod['metadata']['labels']['azure.workload.identity/use'])

    def test_remote_failure_is_not_success(self):
        hub, west = Mock(), Mock()
        hub.request.return_value = {'metadata': {'generation': 1}, 'status': {
            'conditions': [{'type': 'ResourcePlacementScheduled', 'status': 'True', 'observedGeneration': 1}],
            'placementStatuses': [{'clusterName': 'west', 'conditions': [{'type': 'Scheduled', 'status': 'True'}]}]}}
        west.request.return_value = {'metadata': {'labels': {'demo.kubefleet.io/run': 'job'}},
                                     'status': {'conditions': [{'type': 'Failed', 'status': 'True'}]}}
        with self.assertRaisesRegex(RuntimeError, 'training failed'):
            wait_for_training(hub, {'west': west}, 'job', 'west', timeout=1)

    def test_compiled_graph_keeps_all_five_dependencies(self):
        import yaml
        from kfp import compiler
        spec = importlib.util.spec_from_file_location('blob_pipeline', HERE/'pipeline.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'pipeline.yaml'
            compiler.Compiler().compile(module.build('cpu:test', 'gpu:test'), str(path))
            pipeline, platform = list(yaml.safe_load_all(path.read_text()))
        tasks = pipeline['root']['dag']['tasks']
        self.assertEqual(5, len(tasks))
        for downstream, upstream in [('validate-data','prepare-data'), ('train-remotely','validate-data'),
                                      ('evaluate-model','train-remotely'), ('publish-results','evaluate-model')]:
            self.assertIn(upstream, tasks[downstream]['dependentTasks'])
        executors = platform['platforms']['kubernetes']['deploymentSpec']['executors']
        mounted = [name for name, config in executors.items() if config.get('secretAsVolume')]
        self.assertEqual(['exec-train-remotely'], mounted)


if __name__ == '__main__': unittest.main()
