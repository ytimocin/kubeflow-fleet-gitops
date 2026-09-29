"""Write short-lived, namespace-scoped API connections for the demo pipeline."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def connection(kubeconfig, service_account):
    base = ['kubectl', '--kubeconfig', kubeconfig]
    config = json.loads(subprocess.check_output(
        base + ['config', 'view', '--minify', '--flatten', '--raw', '-o', 'json']))
    cluster = config['clusters'][0]['cluster']
    if not cluster['server'].startswith('https://') or not cluster.get('certificate-authority-data'):
        raise ValueError('An HTTPS endpoint and embedded CA certificate are required')
    token = subprocess.check_output(base + [
        '-n', 'pipeline-training', 'create', 'token', service_account,
        '--duration=1h'], text=True).strip()
    return {'server': cluster['server'], 'ca': cluster['certificate-authority-data'], 'token': token}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub', required=True, help='Hub kubeconfig path')
    parser.add_argument('--member', action='append', required=True, metavar='NAME=KUBECONFIG')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    members = dict(value.split('=', 1) for value in args.member)
    if len(members) != len(args.member):
        parser.error('Member names must be unique')
    result = {'hub': connection(args.hub, 'pipeline-submitter'),
              'members': {name: connection(path, 'pipeline-observer')
                          for name, path in members.items()}}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL prevents overwriting an unexpected existing file or following a symlink.
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(result, stream)
    print(f'Wrote {output}; tokens requested for 1 hour. Do not commit this file.')


if __name__ == '__main__':
    main()
