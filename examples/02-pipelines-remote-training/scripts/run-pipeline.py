"""Submit to the local Kubeflow demo's Pipelines API and wait for completion."""
import argparse
from datetime import datetime, timezone
import getpass
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin

import kfp
import requests


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = ''
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.action = attrs.get('action', '')
        if tag == 'input' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')


def submit(args, password):
    session = requests.Session()
    page = session.get(args.host + '/oauth2/start', timeout=30)
    page.raise_for_status()
    form = LoginForm()
    form.feed(page.text)
    if 'login' not in form.fields:
        raise RuntimeError('Expected the demo Dex login form; check the port-forward and authentication setup')
    form.fields.update(login=args.username, password=password)
    page = session.post(urljoin(page.url, form.action), data=form.fields, timeout=30)
    page.raise_for_status()
    if 'Kubeflow Central Dashboard' not in page.text:
        raise RuntimeError('Login did not reach the Kubeflow dashboard')
    cookies = '; '.join(c.name + '=' + c.value for c in session.cookies)
    client = kfp.Client(host=args.host + '/pipeline', cookies=cookies, namespace=args.namespace)
    run = client.create_run_from_pipeline_package(
        args.pipeline, arguments={},
        run_name='remote-gpu-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'),
        experiment_name='Fleet remote GPU training', namespace=args.namespace,
        enable_caching=False,
    )
    record = {'run_id': run.run_id, 'namespace': args.namespace, 'state': 'SUBMITTED'}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('Pipeline run ID:', run.run_id, flush=True)
    result = client.wait_for_run_completion(run.run_id, timeout=1200, sleep_duration=10)
    record['state'] = result.state
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('Pipeline state:', result.state, flush=True)
    if result.state != 'SUCCEEDED':
        raise RuntimeError('Pipeline did not succeed; inspect its task logs before retrying')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='http://127.0.0.1:8080')
    parser.add_argument('--namespace', default='kubeflow-user-example-com')
    parser.add_argument('--username', default='user@example.com')
    parser.add_argument('--pipeline', default='.state/remote-training-pipeline.yaml')
    parser.add_argument('--output', default='.state/remote-pipeline-run.json')
    args = parser.parse_args()
    submit(args, getpass.getpass('Kubeflow demo password: '))


if __name__ == '__main__':
    main()
