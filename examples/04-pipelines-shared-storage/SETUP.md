# Prepare the shared-storage pipeline

Complete [shared setup](../../shared/SETUP.md) and [Kubeflow on East](../../shared/KUBEFLOW.md), or reuse an environment with both. No new cluster is needed.

You need Python 3.11, permission to create storage/ACR/managed identities and role assignments, and permission to run ACR Tasks builds.

## 1. Connect and choose resource names

Follow [Connect](../../shared/CONNECT.md) first. It defines `SUBSCRIPTION`, `RG`, `EAST`, `WEST`, and `STATE`, and downloads the three kubeconfigs. Keep that `STATE` path; no file copying is needed.

In the same terminal, from the repository root:

```bash
export EXAMPLE="$PWD/examples/04-pipelines-shared-storage"
export PROFILE=kubeflow-user-example-com
export STORAGE_ACCOUNT='<unique-name-3-to-24-lowercase-letters-or-digits>'
export REGISTRY='<unique-name-5-to-50-letters-or-digits>'
export STORAGE_REGION=eastus2
python3.11 -m venv .venv
.venv/bin/pip install -r "$EXAMPLE/requirements.txt" -r "$EXAMPLE/requirements-runtime.txt"
east -n kubeflow rollout status deployment/ml-pipeline --timeout=600s
east get namespace "$PROFILE"
west get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Expect Pipelines to be ready, the profile namespace to exist, and West to expose at least one GPU. Use fresh, globally unique storage and registry names.

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
```

The setup script creates the `fleet-demo4` Blob container, two managed identities and their access roles, image-pull access, and the `blob-training` namespace and Fleet API permissions. East uses service account `blob-pipeline`; West uses `blob-trainer`.

Blob access uses Workload Identity with container-scoped read/write permissions. The separate Fleet API credentials are created when you run the demo. Permissions may take a few minutes to propagate.

## 4. Build images and compile

ACR Tasks builds Linux/amd64 CPU and GPU images with dependencies installed ahead of time. The build script resolves image digests before compiling.

```bash
bash "$EXAMPLE/scripts/build.sh"
```

This writes `$STATE/pipeline.yaml`. The GPU image uses PyTorch 2.6.0/CUDA 12.4; CPU tasks use Python 3.11 and NumPy. ACR Tasks availability and permission are required. An equivalent local `docker buildx build --platform linux/amd64 --push` can be used if your subscription disallows ACR Tasks.

Setup is complete. Continue with [run the pipeline](README.md#2-run-the-pipeline).

## 5. Optional: browse files in Azure Portal

In Azure Portal, open the storage account → **Data storage → Containers → fleet-demo4 → runs**. The folder is the first 24 hexadecimal characters of SHA-256 of the pipeline run ID. Portal access requires a Blob data role for your signed-in user; platform resource-management access alone is insufficient.

To give your user read-only access to the container:

```bash
user_id="$(az ad signed-in-user show --query id -o tsv)"
account_id="$(az storage account show --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$STORAGE_ACCOUNT" --query id -o tsv)"
az role assignment create --subscription "$SUBSCRIPTION" \
  --assignee-object-id "$user_id" --assignee-principal-type User \
  --role 'Storage Blob Data Reader' \
  --scope "$account_id/blobServices/default/containers/fleet-demo4" -o none
```

If your organization blocks the user lookup, set `user_id` to your Entra user object ID from Azure Portal instead.

## References

- [AKS Workload Identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [Blob Storage Python SDK](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python)
- [Fleet ResourcePlacement](https://kubefleet.dev/docs/concepts/rp/)
