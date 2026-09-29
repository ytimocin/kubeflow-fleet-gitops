"""Submit via Fleet, discover the selected member, and wait for training success."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NAMESPACE = 'pipeline-training'
JOB_PATH = f'/apis/kubeflow.org/v1/namespaces/{NAMESPACE}/pytorchjobs'
RP_PATH = f'/apis/placement.kubernetes-fleet.io/v1/namespaces/{NAMESPACE}/resourceplacements'
RUN_LABEL = 'demo.kubefleet.io/run'


class Api:
    def __init__(self, config):
        self.server = config['server'].rstrip('/')
        self.token = config['token']
        self.context = ssl.create_default_context(
            cadata=base64.b64decode(config['ca']).decode())

    def request(self, method, path, body=None, text=False):
        request = Request(self.server + path, method=method,
                          headers={'Authorization': 'Bearer ' + self.token,
                                   'Content-Type': 'application/json'},
                          data=json.dumps(body).encode() if body is not None else None)
        # Reads can be retried; writes are never blindly retried after an ambiguous response.
        for attempt in range(3):
            try:
                with urlopen(request, context=self.context, timeout=30) as response:
                    raw = response.read().decode()
                    return raw if text else json.loads(raw)
            except HTTPError as error:
                if method == 'GET' and error.code == 404:
                    return None
                if method == 'GET' and (error.code == 429 or error.code >= 500) and attempt < 2:
                    time.sleep(2)
                    continue
                raise RuntimeError(f'{method} {path}: HTTP {error.code}; check access/token expiry and API health') from None
            except (URLError, TimeoutError):
                if method == 'GET' and attempt < 2:
                    time.sleep(2)
                    continue
                raise RuntimeError(f'{method} {path}: API connection failed; inspect the run before retrying') from None


def prepare(job_template, placement_template, run_id):
    if not run_id or '{{' in run_id:
        raise ValueError('A resolved, nonempty pipeline run ID is required')
    run_key = hashlib.sha256(run_id.encode()).hexdigest()[:24]
    name = 'gpu-' + run_key
    job, placement = copy.deepcopy(job_template), copy.deepcopy(placement_template)
    for obj in (job, placement):
        obj['metadata'] = {'name': name, 'namespace': NAMESPACE, 'labels': {RUN_LABEL: run_key}}
    placement['spec']['resourceSelectors'][0]['name'] = name
    return name, job, placement


def create_once(api, path, obj):
    existing = api.request('GET', path + '/' + obj['metadata']['name'])
    if existing is not None:
        if existing['metadata'].get('labels', {}).get(RUN_LABEL) != obj['metadata']['labels'][RUN_LABEL]:
            raise RuntimeError('Refusing to reuse an object owned by a different run')
        return
    api.request('POST', path, obj)


def selected_member(placement):
    generation = placement['metadata']['generation']
    current = any(c['type'] == 'ResourcePlacementScheduled' and c['status'] == 'True'
                  and c.get('observedGeneration') == generation
                  for c in placement.get('status', {}).get('conditions', []))
    if not current:
        return None
    selected = [s['clusterName'] for s in placement.get('status', {}).get('placementStatuses', [])
                if any(c['type'] == 'Scheduled' and c['status'] == 'True'
                       for c in s.get('conditions', []))]
    if len(selected) > 1:
        raise RuntimeError('Expected exactly one selected cluster')
    return selected[0] if selected else None


def run(hub, members, job_template, placement_template, run_id, timeout=900,
        poll_interval=5, clock=time.monotonic, sleep=time.sleep):
    name, job, placement = prepare(job_template, placement_template, run_id)
    create_once(hub, JOB_PATH, job)
    create_once(hub, RP_PATH, placement)
    print(f'Submitted {name} to Fleet: choose one labeled GPU worker', flush=True)
    deadline = clock() + timeout
    selected = None
    while clock() < deadline:
        current = hub.request('GET', RP_PATH + '/' + name)
        if current is None:
            raise RuntimeError('Placement was deleted while the pipeline was waiting')
        target = selected_member(current)
        if target:
            if selected is not None and selected != target:
                raise RuntimeError('Selected member changed during training; inspect both clusters')
            if target not in members:
                raise RuntimeError(f'No read connection configured for selected member {target}')
            if selected is None:
                print(f'Fleet selected {target}', flush=True)
            selected = target
            member = members[target]
            remote = member.request('GET', JOB_PATH + '/' + name)
            if remote:
                if remote['metadata'].get('labels', {}).get(RUN_LABEL) != job['metadata']['labels'][RUN_LABEL]:
                    raise RuntimeError('Remote job does not belong to this pipeline run')
                conditions = remote.get('status', {}).get('conditions', [])
                if any(c['type'] == 'Failed' and c['status'] == 'True' for c in conditions):
                    raise RuntimeError(f'Training failed on {target}: {name}')
                if any(c['type'] == 'Succeeded' and c['status'] == 'True' for c in conditions):
                    query = urlencode({'labelSelector': 'training.kubeflow.org/job-name=' + name})
                    pods = member.request('GET', f'/api/v1/namespaces/{NAMESPACE}/pods?{query}')
                    masters = [p for p in pods['items'] if p['metadata']['name'] == name + '-master-0']
                    if len(masters) != 1:
                        raise RuntimeError('Expected one retained training pod for GPU evidence')
                    log = member.request('GET', f'/api/v1/namespaces/{NAMESPACE}/pods/{name}-master-0/log?container=pytorch', text=True)
                    if not log or 'TRAINING_SUCCEEDED device=cuda' not in log:
                        raise RuntimeError('Training reported success but CUDA evidence was missing')
                    gpu = next((line for line in log.splitlines() if line.startswith('GPU=')), '')
                    if not gpu:
                        raise RuntimeError('GPU device evidence was missing')
                    print(log, flush=True)
                    result = {'cluster': target, 'job': name, 'namespace': NAMESPACE,
                              'state': 'Succeeded', 'gpu': gpu}
                    print('REMOTE_TRAINING_SUCCEEDED ' + json.dumps(result), flush=True)
                    return result
        sleep(poll_interval)
    raise TimeoutError(f'Training did not finish within {timeout}s; inspect placement and member job {name}')


def main():
    connections_path, run_id, job_json, placement_json, output = sys.argv[1:]
    config = json.loads(Path(connections_path).read_text())
    result = run(Api(config['hub']), {n: Api(c) for n, c in config['members'].items()},
                 json.loads(job_json), json.loads(placement_json), run_id)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))


if __name__ == '__main__':
    main()
