"""Submit a real PyTorchJob through Fleet, then verify its remote result."""
import argparse
import json
from pathlib import Path
import time
from fleet_api import Api, create_once, selected_member, JOB_PATH, RP_PATH, NAMESPACE
from storage import Store, run_prefix


def resources(run_id, target, image, account, container, validated):
    name = 'blob-' + run_prefix(run_id).split('/')[1]
    metadata = {'name': name, 'namespace': NAMESPACE,
                'labels': {'demo.kubefleet.io/run': name}}
    job = {'apiVersion': 'kubeflow.org/v1', 'kind': 'PyTorchJob', 'metadata': metadata,
           'spec': {'runPolicy': {'cleanPodPolicy': 'None', 'activeDeadlineSeconds': 1200},
                    'pytorchReplicaSpecs': {'Master': {'replicas': 1, 'restartPolicy': 'Never',
                    'template': {'metadata': {'labels': {'azure.workload.identity/use': 'true'},
                       'annotations': {'sidecar.istio.io/inject': 'false'}},
                    'spec': {'serviceAccountName': 'blob-trainer',
                       'nodeSelector': {'kubernetes.azure.com/accelerator': 'nvidia'},
                       'tolerations': [
                           {'key': 'sku', 'operator': 'Equal', 'value': 'gpu', 'effect': 'NoSchedule'},
                           {'key': 'kubernetes.azure.com/scalesetpriority', 'operator': 'Equal',
                            'value': 'spot', 'effect': 'NoSchedule'}],
                       'containers': [{'name': 'pytorch', 'image': image,
                          'command': ['python', '/app/train.py'],
                          'args': ['--account', account, '--container', container,
                                   '--run-id', run_id, '--validated', json.dumps(validated)],
                          'resources': {'requests': {'cpu': '500m', 'memory': '1Gi', 'nvidia.com/gpu': 1},
                                        'limits': {'cpu': '2', 'memory': '4Gi', 'nvidia.com/gpu': 1}}}]}}}}}}
    placement = {'apiVersion': 'placement.kubernetes-fleet.io/v1', 'kind': 'ResourcePlacement',
                 'metadata': metadata, 'spec': {'resourceSelectors': [
                     {'group': 'kubeflow.org', 'version': 'v1', 'kind': 'PyTorchJob', 'name': name}],
                     'policy': {'placementType': 'PickFixed', 'clusterNames': [target]}}}
    return name, job, placement


def wait_for_training(hub, members, name, target, timeout=1500):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        placement = hub.request('GET', RP_PATH + '/' + name)
        if placement is None: raise RuntimeError('Placement disappeared')
        selected = selected_member(placement)
        if selected:
            if selected != target: raise RuntimeError('Unexpected target selected')
            member = members[selected]
            job = member.request('GET', JOB_PATH + '/' + name)
            if job:
                if job['metadata'].get('labels', {}).get('demo.kubefleet.io/run') != name:
                    raise RuntimeError('Remote job belongs to another run')
                conditions = job.get('status', {}).get('conditions', [])
                if any(c['type'] == 'Failed' and c['status'] == 'True' for c in conditions):
                    raise RuntimeError('Remote GPU training failed')
                if any(c['type'] == 'Succeeded' and c['status'] == 'True' for c in conditions):
                    log = member.request('GET', f'/api/v1/namespaces/{NAMESPACE}/pods/{name}-master-0/log?container=pytorch', text=True)
                    if not log or 'TRAINING_SUCCEEDED device=cuda' not in log:
                        raise RuntimeError('Missing CUDA training evidence')
                    refs = [json.loads(line.removeprefix('TRAINING_RESULT '))
                            for line in log.splitlines() if line.startswith('TRAINING_RESULT ')]
                    if len(refs) != 1: raise RuntimeError('Expected one training artifact manifest')
                    print(log, flush=True)
                    return {'cluster': selected, 'job': name, 'manifest': refs[0]}
        time.sleep(5)
    raise TimeoutError('Remote training timed out; use the cleanup guide to stop its job')


def main():
    p = argparse.ArgumentParser()
    for name in ['account', 'container', 'run-id', 'validated', 'target', 'image', 'output']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--connections', default='/fleet-access/connections.json')
    a = p.parse_args()
    connections = json.loads(Path(a.connections).read_text())
    if a.target not in connections['members']: raise ValueError('No observer connection for target')
    hub = Api(connections['hub'])
    members = {n: Api(c) for n, c in connections['members'].items()}
    name, job, placement = resources(a.run_id, a.target, a.image, a.account, a.container, json.loads(a.validated))
    create_once(hub, JOB_PATH, job)
    create_once(hub, RP_PATH, placement)
    print(f'Submitted {name} and its ResourcePlacement to the hub; target={a.target}', flush=True)
    result = wait_for_training(hub, members, name, a.target)
    manifest = Store(a.account, a.container).get_json(result['manifest'], run_prefix(a.run_id))
    if manifest['run_id'] != a.run_id: raise ValueError('Artifact run identity mismatch')
    output = Path(a.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result))
    print('REMOTE_TRAINING_SUCCEEDED ' + json.dumps(result), flush=True)


if __name__ == '__main__': main()
