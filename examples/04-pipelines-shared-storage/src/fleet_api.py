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

NAMESPACE = 'blob-training'
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
