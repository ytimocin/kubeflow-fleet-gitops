# Connect to an existing Fleet

> Connect your terminal to the correct clusters and check that their GPUs are available.

For a prepared environment, run these commands in **Bash or zsh** from the repository root. For new infrastructure, follow [SETUP.md](SETUP.md) first.

```bash
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

hub get memberclusters
east get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
west get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Expect two joined, healthy members and at least one allocatable GPU on each. The manifests use the **Fleet member names** `demo-east` and `demo-west`; adjust your chosen example’s manifests if you join members under different names.

Now open either [Example 1](../examples/01-regional-gpu-training/README.md) or [Example 2](../examples/02-pipelines-remote-training/README.md).
