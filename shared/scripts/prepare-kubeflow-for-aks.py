"""Prepare rendered Kubeflow YAML for AKS without claiming controller-owned fields."""
import argparse
import json
import os
import subprocess
import tempfile

import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('path')
parser.add_argument('--kubeconfig')
args = parser.parse_args()
with open(args.path) as stream:
    objects = list(yaml.load_all(stream, Loader=yaml.CSafeLoader))
kinds = {'MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration'}
live = {}
if args.kubeconfig and any(o and o.get('kind') in kinds for o in objects):
    for kind in sorted(kinds):
        result = subprocess.run(['kubectl', '--kubeconfig', args.kubeconfig, 'get', kind,
                                 '-o', 'json', '--request-timeout=30s'],
                                capture_output=True, text=True, check=True)
        for obj in json.loads(result.stdout)['items']:
            for hook in obj.get('webhooks', []):
                live[(kind, obj['metadata']['name'], hook['name'])] = hook
for obj in objects:
    if obj and obj.get('kind') == 'ClusterRole' and obj.get('aggregationRule'):
        obj.pop('rules', None)
    if not obj or obj.get('kind') not in kinds:
        continue
    for webhook in obj.get('webhooks', []):
        if obj['metadata']['name'] in ('webhook.serving.knative.dev', 'validation.webhook.serving.knative.dev'):
            webhook.pop('rules', None)
        if obj['metadata']['name'] == 'istio-validator-istio-system':
            webhook.pop('failurePolicy', None)
        if any(k.startswith('cert-manager.io/inject-ca-from') for k in obj.get('metadata', {}).get('annotations', {})):
            webhook.get('clientConfig', {}).pop('caBundle', None)
        selector = webhook.setdefault('namespaceSelector', {})
        expressions = selector.setdefault('matchExpressions', [])
        for key, value in [('control-plane', 'true'), ('kubernetes.azure.com/managedby', 'aks')]:
            exclusion = {'key': key, 'operator': 'NotIn', 'values': [value]}
            if exclusion not in expressions:
                expressions.append(exclusion)
        current = live.get((obj['kind'], obj['metadata']['name'], webhook['name']))
        if current:
            current_selector = current.get('namespaceSelector', {})
            # Keep exact list order and additional controller exclusions only when
            # every intended predicate is already present; never discard intent.
            if (all(e in current_selector.get('matchExpressions', []) for e in expressions)
                    and all(current_selector.get('matchLabels', {}).get(k) == v
                            for k, v in selector.get('matchLabels', {}).items())):
                webhook['namespaceSelector'] = current_selector
fd, temporary = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(args.path)))
try:
    with os.fdopen(fd, 'w') as stream:
        yaml.dump_all(objects, stream, Dumper=yaml.CSafeDumper, sort_keys=False)
    os.replace(temporary, args.path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
