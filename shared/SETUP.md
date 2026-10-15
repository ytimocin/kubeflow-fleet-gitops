# Shared infrastructure setup

Create a hub-enabled Fleet and two GPU-enabled AKS members, `demo-east` and `demo-west`. This is the common starting point for all four demos. If your environment already exists, use [Connect](CONNECT.md).

## Before you start

- Install Azure CLI, `kubectl`, `kubelogin`, Git, and Python 3.11.
- Use an Azure subscription where you can create AKS/Fleet resources and assign Azure roles.
- Use a **dedicated resource group** and regions with GPU quota and capacity. Provisioning takes time and incurs charges.
- Run each block from the repository root in the same Bash or zsh terminal. Stop on an error.

## 1. Variables and quota

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

The defaults request one A100 (24 vCPUs) in East and one T4 (4 vCPUs) in West. Change the SKU/region variables to match your quota and available capacity. Spot quota is separate from regular GPU quota; quota alone does not guarantee allocation.

## 2. Create the hub and members

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

In the same terminal, download credentials for the Fleet and members in **your current `$RG`**. This updates the local demo kubeconfig files, including any left over from an earlier run.

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

`hub`, `east`, and `west` are shortcuts for `kubectl` with the matching kubeconfig. Keep this terminal open. Use [Connect](CONNECT.md) in a new terminal.

## 3. Add a GPU pool to each member

Add one **Spot** GPU node per cluster. Spot nodes can be evicted. For regular nodes, omit `--priority Spot`, `--eviction-policy Delete`, and `--spot-max-price -1`; regular GPU quota is required.

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

Install Training Operator **v1.9.2** on members and only its PyTorchJob CRD on the hub. The hub stores jobs; members run them.

### East and West

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

### Hub

```bash
hub apply --server-side -f \
  'https://raw.githubusercontent.com/kubeflow/training-operator/v1.9.2/manifests/base/crds/kubeflow.org_pytorchjobs.yaml'
hub wait crd/pytorchjobs.kubeflow.org --for=condition=Established --timeout=60s
```

Expect `serverside-applied`, then `condition met`. This installs the `kubeflow.org/v1` PyTorchJob API, not an operator or a training workload.

### Verify setup

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

Return to [choose a demo](../README.md#choose-a-demo). For demos 2 and 4, also [install Kubeflow on East](KUBEFLOW.md).

References: [Azure Fleet creation](https://learn.microsoft.com/en-us/azure/kubernetes-fleet/quickstart-create-fleet-and-members), [AKS GPUs](https://learn.microsoft.com/en-us/azure/aks/use-nvidia-gpu), [AKS Spot pools](https://learn.microsoft.com/en-us/azure/aks/spot-node-pool), [Fleet v1 API](https://kubefleet.dev/docs/api-reference/placement.kubernetes-fleet.io/v1/), [Training Operator v1.9.2](https://github.com/kubeflow/training-operator/tree/v1.9.2).

## Cleanup shared infrastructure

This removes **all resources in your dedicated demo resource group**, including Fleet, AKS, and their managed resources. For removing just one example's jobs, use that example's cleanup instructions instead.

```bash
az group delete --name "$RG" --yes --no-wait
```

GPU pools incur charges while allocated; Spot nodes may be evicted.
