"""Prepare isolated Blob/Fleet resources. Explicit environment variables select the target."""
import json
import os
from pathlib import Path
import subprocess
import uuid

HERE = Path(__file__).resolve().parents[1]


def command(args, data=None):
    return subprocess.check_output(args, input=data, text=True).strip()


def main():
    env = {k: os.environ[k] for k in ['SUBSCRIPTION', 'RG', 'EAST', 'WEST', 'STATE',
                                    'STORAGE_ACCOUNT', 'REGISTRY', 'PROFILE']}
    sub, rg = env['SUBSCRIPTION'], env['RG']
    state = Path(env['STATE']); state.mkdir(parents=True, exist_ok=True)
    def az(*args):
        return json.loads(command(['az', *args, '--subscription', sub, '-o', 'json']) or 'null')
    def apply(context, obj):
        command(['kubectl', '--kubeconfig', str(state / context), 'apply', '-f', '-'], json.dumps(obj))
    def assignment(principal, role, scope):
        name = str(uuid.uuid5(uuid.NAMESPACE_URL, principal + role + scope.lower()))
        az('role', 'assignment', 'create', '--name', name, '--assignee-object-id', principal,
           '--assignee-principal-type', 'ServicePrincipal', '--role', role, '--scope', scope)
    # Read/validate existing resources instead of changing their security configuration on reruns.
    account = az('storage', 'account', 'show', '-g', rg, '-n', env['STORAGE_ACCOUNT'])
    if account.get('allowBlobPublicAccess') is not False or account.get('allowSharedKeyAccess') is not False:
        raise ValueError('Use a dedicated storage account with public blobs and Shared Key disabled')
    registry = az('acr', 'show', '-g', rg, '-n', env['REGISTRY'])
    container = 'fleet-demo4'
    container_id = account['id'] + '/blobServices/default/containers/' + container
    az('rest', '--method', 'put', '--url', 'https://management.azure.com' + container_id + '?api-version=2023-05-01',
       '--body', json.dumps({'properties': {'publicAccess': 'None'}}))
    config = {'account': env['STORAGE_ACCOUNT'], 'container': container,
              'registry': registry['loginServer'], 'profile': env['PROFILE'], 'identities': {}}
    # This demo deliberately targets West by name and does not modify existing member labels.
    apply('hub', {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'blob-training'}})
    apply('hub', {'apiVersion': 'placement.kubernetes-fleet.io/v1', 'kind': 'ClusterResourcePlacement',
        'metadata': {'name': 'blob-training-namespace'}, 'spec': {'resourceSelectors': [
            {'group': '', 'version': 'v1', 'kind': 'Namespace', 'name': 'blob-training', 'selectionScope': 'NamespaceOnly'}],
            'policy': {'placementType': 'PickFixed', 'clusterNames': [env['WEST']]}}})
    command(['kubectl', '--kubeconfig', str(state/'hub'), 'wait', 'crp/blob-training-namespace',
             '--for=condition=ClusterResourcePlacementAvailable', '--timeout=300s'])
    for context, cluster_name, namespace, sa in [
        ('east', env['EAST'], env['PROFILE'], 'blob-pipeline'),
        ('west', env['WEST'], 'blob-training', 'blob-trainer')]:
        cluster = az('aks', 'show', '-g', rg, '-n', cluster_name)
        if not (cluster.get('securityProfile') or {}).get('workloadIdentity', {}).get('enabled'):
            raise ValueError(f'Enable Workload Identity on {cluster_name} first')
        identity = az('identity', 'create', '-g', rg, '-n', 'fleet-demo4-' + context,
                      '--location', account['location'], '--tags', 'demo=kubeflow-fleet-demo4')
        az('identity', 'federated-credential', 'create', '-g', rg, '--identity-name', identity['name'],
           '-n', 'blob-training', '--issuer', cluster['oidcIssuerProfile']['issuerUrl'],
           '--subject', f'system:serviceaccount:{namespace}:{sa}', '--audiences', 'api://AzureADTokenExchange')
        assignment(identity['principalId'], 'Storage Blob Data Contributor', container_id)
        assignment(cluster['identityProfile']['kubeletidentity']['objectId'], 'AcrPull', registry['id'])
        apply(context, {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
            'name': sa, 'namespace': namespace,
            'annotations': {'azure.workload.identity/client-id': identity['clientId']}}})
        config['identities'][context] = identity['clientId']
    # Dedicated pipeline SA needs the normal KFP/Argo permissions in its profile namespace.
    apply('east', {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding',
        'metadata': {'name': 'blob-pipeline', 'namespace': env['PROFILE']},
        'subjects': [{'kind': 'ServiceAccount', 'name': 'blob-pipeline', 'namespace': env['PROFILE']}],
        'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'kubeflow-edit'}})
    for context, manifest in [('hub', 'hub-access.yaml'), ('west', 'member-access.yaml')]:
        command(['kubectl', '--kubeconfig', str(state/context), 'apply', '-f', str(HERE/'manifests'/manifest)])
    (state/'demo4-config.json').write_text(json.dumps(config, indent=2)+'\n')
    print('Blob storage, identities, namespace, and scoped Fleet API access are configured.')


if __name__ == '__main__': main()
