"""Blob objects are immutable within a run; every reference carries a checksum."""
import hashlib
import json
import re


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def run_prefix(run_id):
    if not run_id or '{{' in run_id:
        raise ValueError('A resolved pipeline run ID is required')
    return 'runs/' + hashlib.sha256(run_id.encode()).hexdigest()[:24] + '/'


def check_ref(ref, prefix):
    if not ref['blob'].startswith(prefix) or '..' in ref['blob'].split('/'):
        raise ValueError('Artifact belongs to another run')
    if not re.fullmatch('[0-9a-f]{64}', ref['sha256']):
        raise ValueError('Invalid artifact checksum')


class Store:
    def __init__(self, account, container):
        from azure.identity import WorkloadIdentityCredential
        from azure.storage.blob import BlobServiceClient
        if not re.fullmatch('[a-z0-9]{3,24}', account):
            raise ValueError('Expected an Azure Storage account name')
        self.container = BlobServiceClient(
            f'https://{account}.blob.core.windows.net',
            credential=WorkloadIdentityCredential()).get_container_client(container)

    def put(self, name, data):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings
        blob = self.container.get_blob_client(name)
        try:
            blob.upload_blob(data, overwrite=False, content_settings=ContentSettings(
                content_type='application/json' if name.endswith('.json') else 'application/octet-stream'))
        except ResourceExistsError:
            if blob.download_blob().readall() != data:
                raise ValueError(f'Refusing to overwrite a different artifact: {name}') from None
        return {'blob': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    def get(self, ref, prefix):
        check_ref(ref, prefix)
        data = self.container.download_blob(ref['blob']).readall()
        if len(data) != ref['bytes'] or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError(f'Artifact checksum mismatch: {ref["blob"]}')
        return data

    def put_json(self, name, value):
        return self.put(name, encode(value))

    def get_json(self, ref, prefix):
        return json.loads(self.get(ref, prefix))
