# Connect to an existing Fleet

Use this whenever you open a new terminal. Run from the repository root in Bash or zsh. For new infrastructure, follow [SETUP.md](SETUP.md) first.

Your existing environment needs a hub-enabled Fleet, joined members, a working GPU/device plugin and Training Operator on each member, and the PyTorchJob CRD on the hub. The examples use Fleet member names `demo-east` and `demo-west`; change their manifests if yours differ.

## 1. Set your names and connect

Replace the first three values. `EAST` and `WEST` are AKS names and, in these guides, also Fleet member names. If you already use a different `STATE` directory, use that path below. Keep it throughout setup and the demo.

```bash
az login
az extension add --name fleet --upgrade
export SUBSCRIPTION='<your-subscription-id>'
export RG='<your-demo-resource-group>'
export FLEET='<your-fleet-name>'
export EAST=demo-east
export WEST=demo-west
export SHARED="$PWD/shared"
export STATE="$PWD/.state"
mkdir -p "$STATE"
chmod 700 "$STATE"
az account set --subscription "$SUBSCRIPTION"
az fleet get-credentials -g "$RG" -n "$FLEET" --file "$STATE/hub" --overwrite-existing
az aks get-credentials -g "$RG" -n "$EAST" --file "$STATE/east" --overwrite-existing
az aks get-credentials -g "$RG" -n "$WEST" --file "$STATE/west" --overwrite-existing
kubelogin convert-kubeconfig -l azurecli --kubeconfig "$STATE/hub"
chmod 600 "$STATE/hub" "$STATE/east" "$STATE/west"
hub() { kubectl --kubeconfig "$STATE/hub" "$@"; }
east() { kubectl --kubeconfig "$STATE/east" "$@"; }
west() { kubectl --kubeconfig "$STATE/west" "$@"; }

```

`hub`, `east`, and `west` are shell functions that call `kubectl` with the right credentials.

## 2. Check readiness

```bash
hub get memberclusters
hub get crd pytorchjobs.kubeflow.org
east -n kubeflow rollout status deployment/training-operator --timeout=300s
west -n kubeflow rollout status deployment/training-operator --timeout=300s
east get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
west get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Expect joined members, ready Training Operator deployments, and at least one allocatable GPU on each member. If prerequisites are missing, complete the corresponding section in [shared setup](SETUP.md).

Return to [choose a demo](../README.md#choose-a-demo). Demos 2 and 4 also require [Kubeflow on East](KUBEFLOW.md); Demo 3 adds a separate `newmember` connection.
