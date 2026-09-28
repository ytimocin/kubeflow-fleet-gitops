# Regional placement of Kubeflow GPU training jobs

**Show:** submit one PyTorchJob to a Fleet hub, run it on a GPU in East US 2, then change its placement to West US 2 and observe a new GPU execution.

```text
kubectl → Fleet hub (PyTorchJob + ResourcePlacement)
                    ├── demo-east → Training Operator → NVIDIA GPU
                    └── demo-west → Training Operator → NVIDIA GPU
```

This addresses regional GPU access using the Training Operator resource model. The example deliberately uses explicit `PickFixed` targets: it does not demonstrate automatic GPU-capacity selection or an unchanged pipeline submission path. The GPU workload is small synthetic training with no external dataset.

## 1. Connect

First time: follow [SETUP.md](SETUP.md) to create the Fleet and two members, add GPUs, and install Training Operator. For a prepared environment, set the following values in **Bash or zsh**, from the repository root:

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

## 2. Create the namespace on both members

```bash
hub apply -f "$DEMO/manifests/namespace.yaml"
hub wait crp/gpu-training-namespace \
  --for=condition=ClusterResourcePlacementAvailable --timeout=180s
east get namespace gpu-training
west get namespace gpu-training
```

The CRP uses `NamespaceOnly`: it distributes the namespace shell. The separate ResourcePlacement below controls the training job.

## 3. Run the job in the first region

On a fresh demo, create the source job and placement. Use the reset commands below before repeating this section; applying an already-completed job does not rerun it.

```bash
hub create -f "$DEMO/manifests/pytorchjob.yaml"
hub create -f "$DEMO/manifests/placement.yaml"
hub -n gpu-training get resourceplacement gpu-training -o wide
east -n gpu-training wait --for=create pytorchjob/regional-gpu-training --timeout=180s
east -n gpu-training wait --for=condition=Succeeded \
  pytorchjob/regional-gpu-training --timeout=900s
east -n gpu-training logs regional-gpu-training-master-0 -c pytorch \
  | tee "$STATE/east-training.log"
east -n gpu-training get pods -o wide
west -n gpu-training get pytorchjobs
```

Expect a GPU name (for example `GPU=Tesla T4`), decreasing loss, and `TRAINING_SUCCEEDED device=cuda`. The code asserts CUDA availability and trains a model on the GPU. West should have no job yet.

Fleet placement status describes propagation. **Read PyTorchJob `Succeeded` and logs on the member to prove training finished.** PyTorchJob is a custom resource: Fleet can report it available while its training pod is still pending. The underlying Work condition reports `reason: NotTrackable`; Fleet assumes the applied resource is available. This is a health-tracking limitation, not proof that a GPU was allocated. No Training Operator runs on the hub, and the hub source job does not automatically receive member training status.

## 4. Run the same definition in the other region

After East has succeeded and you have saved its logs:

```bash
hub -n gpu-training patch resourceplacement gpu-training --type=merge \
  -p '{"spec":{"policy":{"placementType":"PickFixed","clusterNames":["demo-west"]}}}'
hub -n gpu-training get resourceplacement gpu-training -o yaml
west -n gpu-training wait --for=create pytorchjob/regional-gpu-training --timeout=300s
west -n gpu-training wait --for=condition=Succeeded \
  pytorchjob/regional-gpu-training --timeout=900s
west -n gpu-training logs regional-gpu-training-master-0 -c pytorch \
  | tee "$STATE/west-training.log"
east -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
east -n gpu-training get pods
west -n gpu-training get pods -o wide
```

The source definition stays on the hub. Fleet removes its managed job from East and creates it on West. West starts from scratch: **this is resource relocation and a new training execution, not live migration or checkpoint recovery.** Placement changes are asynchronous; this sequence waits for the first execution to finish before switching. Do not use this as an exactly-once handoff for active production jobs.

## 5. Optional: open Kubeflow

[Dashboard setup and access](DASHBOARD.md). The dashboard lives on East and shows its local Kubeflow resources. It is not a Fleet-wide view of remote training. Use the member commands above for GPU job completion and logs.

## Reset for another rehearsal

These commands delete only this example's job and placement, preserving the namespace and infrastructure. Wait for cleanup before recreating the source job.

```bash
hub -n gpu-training delete resourceplacement gpu-training --ignore-not-found --wait=true
east -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
west -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
east -n gpu-training wait --for=delete pod -l training.kubeflow.org/job-name=regional-gpu-training --timeout=180s
west -n gpu-training wait --for=delete pod -l training.kubeflow.org/job-name=regional-gpu-training --timeout=180s
hub -n gpu-training delete pytorchjob regional-gpu-training --ignore-not-found
```

Then repeat section 3. `kubectl wait --for=delete` is satisfied when the named object is already absent.

## If something is stuck

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

## After the demo

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

Reference: [Fleet availability checks](https://kubefleet.dev/docs/concepts/safe-rollout/).

See [validation](VALIDATION.md) for what was actually rehearsed, and [the upcoming pipeline example](../02-pipelines-remote-training/README.md) for preserving pipeline orchestration.
