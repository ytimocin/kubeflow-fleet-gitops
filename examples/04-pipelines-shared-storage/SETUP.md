# Prepare the shared-storage pipeline

Reuse the Fleet hub, East's Kubeflow installation, and West's GPU worker from [shared setup](../../shared/SETUP.md) and [Kubeflow setup](../../shared/KUBEFLOW.md). No new cluster is needed. Use Python 3.11, Azure CLI, kubectl, and access to create managed identities and role assignments in your demo resource group.

## 1. Select your environment

From the repository root, load your existing connection variables. Keep all kubeconfigs and generated credentials under ignored `.state/`.

```bash
export EXAMPLE="$PWD/examples/04-pipelines-shared-storage"
export STATE="$PWD/.state/demo4"
mkdir -p "$STATE"
# Copy your existing hub, east, and west kubeconfig files into this directory.
# Define SUBSCRIPTION, RG, EAST, WEST, and PROFILE for your existing environment.
export PROFILE=kubeflow-user-example-com
export STORAGE_ACCOUNT='<globally-unique-lowercase-name>'
export REGISTRY='<globally-unique-ACR-name>'
export STORAGE_REGION=eastus2
python3.11 -m venv .venv
.venv/bin/pip install -r "$EXAMPLE/requirements.txt" -r "$EXAMPLE/requirements-runtime.txt"
```

Confirm West has an allocatable GPU and East's pipeline services are available. Restore stopped node pools before starting the pipeline.

```bash
kubectl --kubeconfig "$STATE/east" -n kubeflow rollout status deployment/ml-pipeline --timeout=600s
kubectl --kubeconfig "$STATE/west" get nodes \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

## 2. Create dedicated storage and image registry

Use new names for this demo. These resources incur storage, registry, and bandwidth charges; the GPU worker is normally the larger cost.

```bash
az storage account create --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$STORAGE_ACCOUNT" --location "$STORAGE_REGION" --sku Standard_LRS \
  --kind StorageV2 --allow-blob-public-access false --allow-shared-key-access false \
  --min-tls-version TLS1_2 --https-only true --tags demo=kubeflow-fleet-demo4 -o none
az acr create --subscription "$SUBSCRIPTION" -g "$RG" -n "$REGISTRY" \
  --sku Basic --admin-enabled false --tags demo=kubeflow-fleet-demo4 -o none
```

## 3. Enable identity and configure access

Complete the two cluster updates before running setup. Existing OIDC issuers are reused.

```bash
az aks update --subscription "$SUBSCRIPTION" -g "$RG" -n "$EAST" \
  --enable-oidc-issuer --enable-workload-identity -o none
az aks update --subscription "$SUBSCRIPTION" -g "$RG" -n "$WEST" \
  --enable-oidc-issuer --enable-workload-identity -o none
.venv/bin/python "$EXAMPLE/scripts/setup.py"
bash "$EXAMPLE/scripts/refresh-access.sh"
```

Setup creates:

- A private `fleet-demo4` container (through the management API; no account keys).
- Two managed identities, federated to East's `blob-pipeline` and West's `blob-trainer` service accounts, with Blob Data Contributor at this container's scope.
- `AcrPull` for the two AKS kubelet identities on this registry.
- A `blob-training` namespace shell on the hub and West, using a CRP.
- Separate hub submitter and West observer RBAC limited to `blob-training`.
- A dedicated East pipeline service account with the normal `kubeflow-edit` role limited to its profile namespace.

Both storage identities can read/write the demo container; per-stage containers and finer permissions are a production extension. Storage permissions may take several minutes to propagate. The Fleet Secret is mounted only into the submission/waiting task. Its tokens are requested for one hour; refresh before later sessions. Do not share the connections JSON or Secret.

## 4. Build images and compile

ACR Tasks builds Linux/amd64 CPU and GPU images with dependencies installed ahead of time. The build script resolves image digests before compiling.

```bash
bash "$EXAMPLE/scripts/build.sh"
```

This writes `$STATE/pipeline.yaml`. The GPU image uses PyTorch 2.6.0/CUDA 12.4; CPU tasks use Python 3.11 and NumPy. ACR Tasks availability and permission are required. An equivalent local `docker buildx build --platform linux/amd64 --push` can be used if your subscription disallows ACR Tasks.

## 5. Start the pipeline

Keep this port-forward running in another terminal:

```bash
kubectl --kubeconfig "$STATE/east" -n istio-system \
  port-forward svc/istio-ingressgateway 8088:80 --address 127.0.0.1
```

Optionally upload a browsable definition first (once per pipeline name):

```bash
.venv/bin/python "$EXAMPLE/scripts/run-pipeline.py" \
  --pipeline "$STATE/pipeline.yaml" --account "$STORAGE_ACCOUNT" --upload-only
```

This creates **Fleet shared Blob storage** in the Pipelines list without running it. For an existing definition, upload a new version through the UI rather than creating the same name again.

Submit from the repository root:

```bash
.venv/bin/python "$EXAMPLE/scripts/run-pipeline.py" \
  --pipeline "$STATE/pipeline.yaml" --account "$STORAGE_ACCOUNT" \
  --target "$WEST" --namespace "$PROFILE" --output "$STATE/run.json"
```

The helper prompts for the local demo's Dex password and sets **service account `blob-pipeline`**. It does not implement customer enterprise SSO. It prints the run link and waits for completion. The five tasks should become green in sequence. If importing through the UI instead, set the run's service account to `blob-pipeline`; the default account has no Blob identity.

In Azure Portal, open the storage account → **Data storage → Containers → fleet-demo4 → runs**. The folder is the first 24 hexadecimal characters of SHA-256 of the pipeline run ID. Portal access requires a Blob data role for your signed-in user; platform resource-management access alone is insufficient.

To grant the signed-in demo presenter read-only access to this container:

```bash
presenter_id='<your-Entra-user-object-ID>'
account_id="$(az storage account show --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$STORAGE_ACCOUNT" --query id -o tsv)"
az role assignment create --subscription "$SUBSCRIPTION" \
  --assignee-object-id "$presenter_id" --assignee-principal-type User \
  --role 'Storage Blob Data Reader' \
  --scope "$account_id/blobServices/default/containers/fleet-demo4" -o none
```

## References

- [AKS Workload Identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [Blob Storage Python SDK](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python)
- [Fleet ResourcePlacement](https://kubefleet.dev/docs/concepts/rp/)
