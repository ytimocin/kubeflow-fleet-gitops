"""Remove only one run's Fleet placement/job; preserve pipeline history and Blob artifacts."""
import argparse
import hashlib
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', required=True)
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    if not a.run_id or '{{' in a.run_id: raise ValueError('Use the actual pipeline run ID')
    name = 'blob-' + hashlib.sha256(a.run_id.encode()).hexdigest()[:24]
    def kube(context, *args):
        subprocess.run(['kubectl', '--kubeconfig', str(Path(a.state)/context),
                        '-n', 'blob-training', *args], check=True)
    kube('hub', 'delete', 'resourceplacement', name, '--ignore-not-found', '--timeout=180s')
    kube('west', 'wait', '--for=delete', 'pytorchjob/'+name, '--timeout=180s')
    kube('hub', 'delete', 'pytorchjob', name, '--ignore-not-found', '--timeout=180s')
    print('Removed remote work for', a.run_id, '; kept Blob artifacts and pipeline history.')


if __name__ == '__main__': main()
