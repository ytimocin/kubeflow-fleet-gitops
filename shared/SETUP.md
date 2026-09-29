# Shared infrastructure setup

Run from the repository root in Bash or zsh. Requires Azure CLI with `fleet` support, `kubectl`, `kubelogin`, Python 3, Git, and permission to create AKS/Fleet and assign the Fleet data-plane role. Allow provisioning and image-pull time before the meeting.

Use a **dedicated** resource group. Both examples use this same infrastructure. Create it once, then run either example in any order. Fleet does not create GPU capacity or bypass Azure quota.

## 1. Variables and quota

> Choose the regions and GPU types, then check how much GPU capacity your account is allowed to request.

```bash
az login
az extension add --name fleet --upgrade
export SUBSCRIPTION='<your-subscription-id>'
export RG=fleet-gpu-demo
export FLEET=fleet-gpu-demo
export EAST=demo-east
export WEST=demo-west
export EAST_REGION=eastus2
export WEST_REGION=westus2
export EAST_GPU_SKU=Standard_NC24ads_A100_v4
export WEST_GPU_SKU=Standard_NC4as_T4_v3
export SHARED="$PWD/shared"
export STATE="$PWD/.state"
mkdir -p "$STATE"
chmod 700 "$STATE"
az account set --subscription "$SUBSCRIPTION"
for location_sku in "$EAST_REGION:$EAST_GPU_SKU" "$WEST_REGION:$WEST_GPU_SKU"; do
  region="${location_sku%%:*}"
  gpu_sku="${location_sku#*:}"
  printf "Checking quota in %s...\n" "$region"
  az vm list-usage -l "$region" \
    --query "[?contains(name.value,'NC') || name.value=='lowPriorityCores'].{Quota:name.localizedValue,Used:currentValue,Limit:limit}" -o table || break
  printf "Checking %s in %s (this can take a few minutes)...\n" "$gpu_sku" "$region"
  az vm list-skus -l "$region" --size "$gpu_sku" --all \
    --query '[].{SKU:name,Restrictions:restrictions}' -o json || break
done
```

These selections use one A100 / 24 vCPUs in East and one T4 / 4 vCPUs in West. East T4 Spot allocation failed during rehearsal; the A100 is an alternative, not a Fleet requirement. If T4 capacity is available in your first region, set `EAST_GPU_SKU=Standard_NC4as_T4_v3` for a smaller pool. Regular nodes require suitable family and regional quota. Spot uses a separate quota and is interruptible. Quota and unrestricted SKUs do not guarantee allocation capacity. Choose regions where allocation succeeds.

## 2. Create the hub and members

> Create one central Fleet hub and two clusters where the training jobs can run.

Run both AKS creation commands and wait for each to succeed before joining the members. Stop and resolve any error before continuing.

```bash
az group create -n "$RG" -l "$EAST_REGION"
az fleet create -g "$RG" -n "$FLEET" -l "$EAST_REGION" \
  --enable-hub --enable-managed-identity
az aks create -g "$RG" -n "$EAST" -l "$EAST_REGION" \
  --nodepool-name system --node-count 1 --node-vm-size Standard_D4as_v5 \
  --enable-managed-identity --network-plugin azure --network-plugin-mode overlay \
  --generate-ssh-keys
az aks create -g "$RG" -n "$WEST" -l "$WEST_REGION" \
  --nodepool-name system --node-count 1 --node-vm-size Standard_D4as_v5 \
  --enable-managed-identity --network-plugin azure --network-plugin-mode overlay \
  --generate-ssh-keys
```

Join the two existing AKS clusters to Fleet:

```bash
for cluster in "$EAST" "$WEST"; do
  printf "Joining %s to Fleet...\n" "$cluster"
  cluster_id=$(az aks show -g "$RG" -n "$cluster" --query id -o tsv) || break
  az fleet member create -g "$RG" --fleet-name "$FLEET" \
    -n "$cluster" --member-cluster-id "$cluster_id" || break
done
```

After both members join successfully, grant your user access to the hub:

```bash
fleet_id=$(az fleet show -g "$RG" -n "$FLEET" --query id -o tsv)
object_id=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$object_id" \
  --assignee-principal-type User \
  --role 'Azure Kubernetes Fleet Manager RBAC Cluster Admin' --scope "$fleet_id"
```

The role assignment can take a few minutes to propagate. If using a service principal, use its object ID and `ServicePrincipal` instead of `User`.

### Connect kubectl to the three clusters

> Connect your terminal to the hub, East, and West so each command goes to the intended cluster.

In the same terminal, download credentials for the Fleet and members in **your current `$RG`**. This updates the local demo kubeconfig files, including any left over from an earlier rehearsal.

```bash
az fleet get-credentials -g "$RG" -n "$FLEET" --file "$STATE/hub" --overwrite-existing
az aks get-credentials -g "$RG" -n "$EAST" --file "$STATE/east" --overwrite-existing
az aks get-credentials -g "$RG" -n "$WEST" --file "$STATE/west" --overwrite-existing
kubelogin convert-kubeconfig -l azurecli --kubeconfig "$STATE/hub"
chmod 600 "$STATE/hub" "$STATE/east" "$STATE/west"

hub() { kubectl --kubeconfig "$STATE/hub" "$@"; }
east() { kubectl --kubeconfig "$STATE/east" "$@"; }
west() { kubectl --kubeconfig "$STATE/west" "$@"; }

hub get memberclusters
east get nodes
west get nodes
```

`hub`, `east`, and `west` are shell functions, not installed commands. They forward every argument to `kubectl` using the corresponding kubeconfig. For example, `east get nodes` means `kubectl --kubeconfig "$STATE/east" get nodes`. Keep using this terminal for the remaining steps; in a new terminal, use [Connect](CONNECT.md). GPU nodes are added next.

## 3. Add a GPU pool to each member

> Add one GPU machine to each cluster and make its GPU available to training jobs.

**Choose one option.** If section 1 showed zero regular quota for your selected GPU families, use **Spot** below. Spot nodes can be evicted; the system pools remain regular. Wait for the whole loop to finish successfully before installing the device plugin.

Spot GPUs (used for this rehearsal because regular GPU quota was unavailable):

```bash
for cluster in "$EAST" "$WEST"; do
  printf "Waiting for %s to finish any AKS update...\n" "$cluster"
  az aks wait -g "$RG" -n "$cluster" --updated --interval 15 --timeout 1800 || break
  gpu_sku="$WEST_GPU_SKU"
  if [ "$cluster" = "$EAST" ]; then gpu_sku="$EAST_GPU_SKU"; fi
  az aks nodepool add -g "$RG" --cluster-name "$cluster" \
    --name gpu --mode User --node-count 1 --node-vm-size "$gpu_sku" \
    --os-sku Ubuntu --node-osdisk-size 128 --node-osdisk-type Managed --node-taints sku=gpu:NoSchedule \
    --priority Spot --eviction-policy Delete --spot-max-price -1 \
    --enable-cluster-autoscaler --min-count 1 --max-count 1 || break
done
```

<details>
<summary>Alternative: regular GPUs, only with sufficient family and regional quota</summary>

Regular GPUs (use when quota and capacity are available):

```bash
for cluster in "$EAST" "$WEST"; do
  printf "Waiting for %s to finish any AKS update...\n" "$cluster"
  az aks wait -g "$RG" -n "$cluster" --updated --interval 15 --timeout 1800 || break
  gpu_sku="$WEST_GPU_SKU"
  if [ "$cluster" = "$EAST" ]; then gpu_sku="$EAST_GPU_SKU"; fi
  az aks nodepool add -g "$RG" --cluster-name "$cluster" \
    --name gpu --mode User --node-count 1 --node-vm-size "$gpu_sku" \
    --os-sku Ubuntu --node-osdisk-size 128 --node-osdisk-type Managed --node-taints sku=gpu:NoSchedule || break
done
```

</details>

Install the NVIDIA device plugin; AKS provides the GPU driver with the supported GPU node image. This configuration runs the plugin only on GPU nodes and tolerates the GPU and Spot taints. Do not install a second plugin if your cluster already manages one.

```bash
east apply -k "$SHARED/manifests/device-plugin"
west apply -k "$SHARED/manifests/device-plugin"
east -n nvidia-device-plugin rollout status ds/nvidia-device-plugin-daemonset --timeout=300s
west -n nvidia-device-plugin rollout status ds/nvidia-device-plugin-daemonset --timeout=300s
east get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
west get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Do not continue without at least one allocatable GPU on each member. A DaemonSet with zero desired pods is not GPU validation.

## 4. Install Training Operator on members; only the CRD on the hub

> Teach the hub to store training requests and equip both clusters to carry them out.

The members need **Training Operator** to run jobs. The hub needs only the **PyTorchJob CRD** to store their definitions. Both use the same pinned release, **v1.9.2**.

### On East and West: install the operator

> Install the software that turns a training request into a running job on each cluster.

Skip installation on a member if it already has this operator from the optional full Kubeflow setup.

```bash
east apply --server-side -k \
  'github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.9.2'
west apply --server-side -k \
  'github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.9.2'

east -n kubeflow rollout status deployment/training-operator --timeout=300s
west -n kubeflow rollout status deployment/training-operator --timeout=300s
```

Expect `deployment "training-operator" successfully rolled out` for both members.

### On the hub: install only the job definition

> Let the hub recognize and store training requests without running the training itself.

```bash
hub apply --server-side -f \
  'https://raw.githubusercontent.com/kubeflow/training-operator/v1.9.2/manifests/base/crds/kubeflow.org_pytorchjobs.yaml'
hub wait crd/pytorchjobs.kubeflow.org --for=condition=Established --timeout=60s
```

Expect `serverside-applied`, then `condition met`. This installs the `kubeflow.org/v1` PyTorchJob API, not an operator or a training workload.

### Check the members

> Confirm that both clusters are connected to Fleet.

```bash
hub get memberclusters
```

Both should show `JOINED=True` with recent agent heartbeats. Setup is complete.

<details>
<summary>Optional: check Fleet API compatibility</summary>

```bash
hub api-resources --api-group=placement.kubernetes-fleet.io
```

Look for `resourceplacements` and `clusterresourceplacements` serving `placement.kubernetes-fleet.io/v1`. The namespace-only selector also requires support in your managed Fleet version. This example uses Training Operator's PyTorchJob, not the newer Trainer TrainJob API.

</details>

Choose either [regional GPU training](../examples/01-regional-gpu-training/README.md) or [Pipelines with remote training](../examples/02-pipelines-remote-training/README.md). Neither requires running the other. Example 2 additionally needs [Kubeflow Pipelines on East](KUBEFLOW.md); this is optional for Example 1.

References: [Azure Fleet creation](https://learn.microsoft.com/en-us/azure/kubernetes-fleet/quickstart-create-fleet-and-members), [AKS GPUs](https://learn.microsoft.com/en-us/azure/aks/use-nvidia-gpu), [AKS Spot pools](https://learn.microsoft.com/en-us/azure/aks/spot-node-pool), [Fleet v1 API](https://kubefleet.dev/docs/api-reference/placement.kubernetes-fleet.io/v1/), [Training Operator v1.9.2](https://github.com/kubeflow/training-operator/tree/v1.9.2).

## Cleanup shared infrastructure

> Delete the shared environment only when you are finished with both examples.

This removes **all resources in your dedicated demo resource group**, including Fleet, AKS, and their managed resources. For removing just one example's jobs, use that example's cleanup instructions instead.

```bash
az group delete --name "$RG" --yes --no-wait
```

GPU pools incur charges while allocated; Spot nodes may be evicted.
