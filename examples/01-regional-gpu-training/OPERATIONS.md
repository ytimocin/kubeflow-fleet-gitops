# Connection, reset, and troubleshooting

[Back to the demo](README.md).

## Connect


For a prepared environment, run these commands in **Bash or zsh** from the repository root. For new infrastructure, follow [SETUP.md](SETUP.md) first.

```bash
export SUBSCRIPTION='<your-subscription-id>'
export RG='<your-demo-resource-group>'
export FLEET='<your-fleet-name>'
export EAST=demo-east
export WEST=demo-west
export DEMO="$PWD/examples/01-regional-gpu-training"
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

Expect two joined, healthy members and at least one allocatable GPU on each. The manifests use the **Fleet member names** `demo-east` and `demo-west`; edit both placement manifests if you join members under different names.

## Reset


These commands delete only this example's job and placement, preserving the namespace and infrastructure. Wait for cleanup before recreating the source job.

```bash
hub -n gpu-training delete resourceplacement gpu-training --ignore-not-found --wait=true
east -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
west -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
east -n gpu-training wait --for=delete pod -l training.kubeflow.org/job-name=regional-gpu-training --timeout=180s
west -n gpu-training wait --for=delete pod -l training.kubeflow.org/job-name=regional-gpu-training --timeout=180s
hub -n gpu-training delete pytorchjob regional-gpu-training --ignore-not-found
```

Then repeat [Run in East](README.md#2-run-in-east). `kubectl wait --for=delete` is satisfied when the named object is already absent.

## Troubleshooting


```bash
hub -n gpu-training describe resourceplacement gpu-training
hub -n gpu-training get resourceplacement gpu-training -o yaml
hub -n fleet-member-demo-east get work gpu-training.gpu-training-work \
  -o jsonpath='{.status.manifestConditions[*].conditions}{"\n"}'
east -n gpu-training get pytorchjobs,pods
east -n gpu-training describe pod regional-gpu-training-master-0
east -n gpu-training get events --sort-by=.lastTimestamp
# Repeat with west() when West is selected.
```

`Pending` / insufficient `nvidia.com/gpu`: inspect GPU nodes and the device plugin. `ImagePullBackOff`: inspect pod events and registry connectivity. Placement `Applied=False`: check that the destination has the PyTorchJob CRD and namespace. Placement `Available=True` alone does not prove GPU execution or training success.


PyTorchJob availability is not tracked by Fleet. The Work reports `NotTrackable`; the top-level placement can report `Available=True` while the training pod is Pending. Check the member’s PyTorchJob `Succeeded` condition and logs. The hub source job does not automatically receive member training status. See [Fleet availability checks](https://kubefleet.dev/docs/concepts/safe-rollout/).

## Cleanup


To remove only the example, reset it first, then run:

```bash
hub delete crp gpu-training-namespace --wait=true
hub delete namespace gpu-training
```

To remove **all resources in your dedicated demo resource group**, including Fleet, AKS, and their managed resources:

```bash
az group delete --name "$RG" --yes --no-wait
```

Use that final command only when the whole demo is finished. GPU pools incur charges while allocated; Spot nodes may be evicted before the meeting.

