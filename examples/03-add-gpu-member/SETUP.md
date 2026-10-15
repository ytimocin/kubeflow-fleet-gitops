# Prepare the new GPU cluster

Reuse a hub-enabled Fleet with the PyTorchJob CRD from [shared setup](../../shared/SETUP.md). This guide creates one additional GPU cluster; the [walkthrough](README.md) joins it to Fleet.

## 1. Set the environment

First [connect to your existing Fleet](../../shared/CONNECT.md). In that same terminal, from the repository root:

```bash
export EXPANSION="$PWD/examples/03-add-gpu-member"
export NEW_MEMBER=demo-gpu
export NEW_REGION=westus2
export NEW_GPU_SKU=Standard_NC24ads_A100_v4
```

Check quota and SKU restrictions; neither guarantees immediate allocation:

```bash
az vm list-usage --subscription "$SUBSCRIPTION" -l "$NEW_REGION" \
  --query "[?contains(name.value,'NC') || name.value=='lowPriorityCores'].{Quota:name.localizedValue,Used:currentValue,Limit:limit}" -o table
az vm list-skus --subscription "$SUBSCRIPTION" -l "$NEW_REGION" \
  --size "$NEW_GPU_SKU" --all \
  --query '[].{SKU:name,Restrictions:restrictions}' -o json
```

The example uses one Spot A100 and a regular CPU system node. Spot is interruptible. You can choose another supported NVIDIA GPU SKU/region with available capacity. Regular GPUs additionally need family quota. Do not create a new Fleet or modify East/West pools for this example.

## 2. Create the cluster and GPU pool

Skip cluster creation if **your intended new cluster** already exists. Check its identity and state before reusing it:

```bash
az aks list --subscription "$SUBSCRIPTION" -g "$RG" \
  --query '[].{Name:name,Region:location,State:provisioningState}' -o table
```

For a new name, create and wait for the regular system pool:

```bash
az aks create --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$NEW_MEMBER" -l "$NEW_REGION" \
  --nodepool-name system --node-count 1 --node-vm-size Standard_D4as_v5 \
  --enable-managed-identity --network-plugin azure --network-plugin-mode overlay \
  --generate-ssh-keys -o none
```

Then add the GPU pool. Stop if either command fails; continue only after allocation succeeds and the node exposes a GPU.

```bash
az aks nodepool add --subscription "$SUBSCRIPTION" -g "$RG" \
  --cluster-name "$NEW_MEMBER" --name gpu --mode User \
  --node-count 1 --node-vm-size "$NEW_GPU_SKU" \
  --os-sku Ubuntu --node-osdisk-type Managed --node-osdisk-size 128 \
  --node-taints sku=gpu:NoSchedule \
  --priority Spot --eviction-policy Delete --spot-max-price -1 \
  --enable-cluster-autoscaler --min-count 1 --max-count 1 -o none
```

For a regular GPU pool with sufficient quota, omit the three Spot flags. The autoscaler requests a minimum of one GPU node after eviction, but cannot guarantee replacement capacity. Existing pools should be inspected with `az aks nodepool list` before retrying; do not repeatedly run `az aks create` or a parent-cluster update to repair a failed GPU allocation.

## 3. Connect and install the member prerequisites

```bash
az fleet get-credentials --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$FLEET" --file "$STATE/hub" --overwrite-existing
kubelogin convert-kubeconfig -l azurecli --kubeconfig "$STATE/hub"
az aks get-credentials --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$NEW_MEMBER" --file "$STATE/new-member" --overwrite-existing
chmod 600 "$STATE/hub" "$STATE/new-member"
hub() { kubectl --kubeconfig "$STATE/hub" "$@"; }
newmember() { kubectl --kubeconfig "$STATE/new-member" "$@"; }

newmember apply -k "$SHARED/manifests/device-plugin"
newmember apply --server-side -k \
  'github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.9.2'
newmember -n kubeflow rollout status deployment/training-operator --timeout=300s
newmember -n nvidia-device-plugin rollout status \
  ds/nvidia-device-plugin-daemonset --timeout=300s
newmember wait nodes -l agentpool=gpu --for=condition=Ready --timeout=600s
```

Skip installing a second operator or device plugin when reusing a cluster that already has them. Full Kubeflow, a dashboard, and pipeline credentials are not needed on this member.

Verify actual allocatable GPU capacity, not just a successful DaemonSet rollout:

```bash
newmember get nodes -l agentpool=gpu -o json | python3 -c '
import json, sys
nodes = json.load(sys.stdin)["items"]
assert nodes, "No GPU-pool nodes found"
for node in nodes:
    ready = any(c["type"] == "Ready" and c["status"] == "True"
                for c in node["status"]["conditions"])
    count = int(node["status"]["allocatable"].get("nvidia.com/gpu", 0))
    assert ready and count > 0, "GPU node is not ready with allocatable GPUs"
    print(node["metadata"]["name"], "Ready; allocatable GPUs:", count)
'
hub get crd pytorchjobs.kubeflow.org
```

If the assertion fails, inspect the plugin pods and wait for registration before repeating it. An empty GPU node list or zero desired plugin pods does not pass this check.

## 4. Check readiness to join

```bash
export NEW_CLUSTER_ID="$(az aks show --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$NEW_MEMBER" --query id -o tsv)"
test -n "$NEW_CLUSTER_ID"
az fleet member list --subscription "$SUBSCRIPTION" -g "$RG" \
  --fleet-name "$FLEET" --query '[].{Name:name,State:provisioningState}' -o table
hub get memberclusters
```

Before the first join, the new member should be absent from both lists. If it is already joined, skip joining and continue at [prepare a namespace](README.md#3-prepare-a-namespace-on-the-new-member), or use [repeat registration](OPERATIONS.md#repeat-member-registration).

You can inspect the Fleet's **Members** page and the new AKS cluster's **Node pools** page in Azure Portal. Continue with the [example walkthrough](README.md).
