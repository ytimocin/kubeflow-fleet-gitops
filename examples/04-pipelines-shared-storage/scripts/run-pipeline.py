"""Submit the Blob pipeline using a dedicated workload-identity service account."""
import argparse
from datetime import datetime, timezone
import getpass
import importlib.util
import json
from pathlib import Path
import kfp
import requests


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='http://127.0.0.1:8088')
    p.add_argument('--namespace', default='kubeflow-user-example-com')
    p.add_argument('--username', default='user@example.com')
    p.add_argument('--pipeline', default='.state/demo4/pipeline.yaml')
    p.add_argument('--account', required=True)
    p.add_argument('--container', default='fleet-demo4')
    p.add_argument('--target', default='demo-west')
    p.add_argument('--threshold', type=float, default=0.02)
    p.add_argument('--name', default='Shared data GPU pipeline')
    p.add_argument('--output', default='.state/demo4/run.json')
    p.add_argument('--upload-only', action='store_true', help='Upload a browsable pipeline definition without starting a run')
    a = p.parse_args()
    # Reuse only the demo Dex HTML parser; credentials are entered, never saved.
    path = Path(__file__).resolve().parents[2]/'02-pipelines-remote-training/scripts/run-pipeline.py'
    spec = importlib.util.spec_from_file_location('demo_login', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    session = requests.Session()
    page = session.get(a.host+'/oauth2/start', timeout=30); page.raise_for_status()
    form = module.LoginForm(); form.feed(page.text)
    if 'login' not in form.fields: raise RuntimeError('Expected demo Dex login form')
    form.fields.update(login=a.username, password=getpass.getpass('Kubeflow demo password: '))
    page = session.post(module.urljoin(page.url, form.action), data=form.fields, timeout=30)
    page.raise_for_status()
    if 'Kubeflow Central Dashboard' not in page.text: raise RuntimeError('Login failed')
    client = kfp.Client(host=a.host+'/pipeline', namespace=a.namespace,
        cookies='; '.join(c.name+'='+c.value for c in session.cookies))
    if a.upload_only:
        pipeline = client.upload_pipeline(a.pipeline, pipeline_name='Fleet shared Blob storage',
            description='Five tasks share Blob artifacts: East prepares, West trains through Fleet, East evaluates and publishes.')
        print('Uploaded pipeline:', pipeline.pipeline_id)
        return
    run = client.create_run_from_pipeline_package(a.pipeline, arguments={
        'storage_account': a.account, 'container': a.container,
        'target_member': a.target, 'mse_threshold': a.threshold},
        run_name=a.name, experiment_name='Fleet shared Blob storage', namespace=a.namespace,
        enable_caching=False, service_account='blob-pipeline')
    output = Path(a.output); output.parent.mkdir(parents=True, exist_ok=True)
    record = {'run_id': run.run_id, 'state': 'SUBMITTED', 'submitted_at': datetime.now(timezone.utc).isoformat()}
    output.write_text(json.dumps(record, indent=2)+'\n')
    print('Run:', run.run_id, flush=True)
    print(a.host+'/pipeline/#/runs/details/'+run.run_id, flush=True)
    result = client.wait_for_run_completion(run.run_id, timeout=1800, sleep_duration=10)
    record['state'] = result.state
    output.write_text(json.dumps(record, indent=2)+'\n')
    print('State:', result.state)
    if result.state != 'SUCCEEDED': raise RuntimeError('Inspect the failed task before retrying')


if __name__ == '__main__': main()
