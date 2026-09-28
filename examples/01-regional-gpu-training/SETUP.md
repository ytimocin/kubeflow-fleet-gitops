# One-time Azure setup

Run from the repository root in Bash or zsh. Requires Azure CLI with `fleet` support, `kubectl`, `kubelogin`, Python 3, Git, and permission to create AKS/Fleet and assign the Fleet data-plane role. Allow provisioning and image-pull time before the meeting.

Use a **dedicated** resource group. Two GPU-capable members are sufficient for this example. Fleet does not create GPU capacity or bypass Azure quota.

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
export DEMO="$PWD/examples/01-regional-gpu-training"
export STATE="$PWD/.state"
mkdir -p "$STATE"
chmod 700 "$STATE"
az account set --subscription "$SUBSCRIPTION"
for location_sku in "$EAST_REGION:$EAST_GPU_SKU" "$WEST_REGION:$WEST_GPU_SKU"; do
  region="${location_sku%%:*}"
  gpu_sku="${location_sku#*:}"
  az vm list-usage -l "$region" \
    --query "[?contains(name.value,'NC') || name.value=='lowPriorityCores'].{Quota:name.localizedValue,Used:currentValue,Limit:limit}" -o table
  az vm list-skus -l "$region" --size "$gpu_sku" --all \
    --query '[].{SKU:name,Restrictions:restrictions}' -o json
done
```

These selections use one A100 / 24 vCPUs in East and one T4 / 4 vCPUs in West. East T4 Spot allocation failed during rehearsal; the A100 is an alternative, not a Fleet requirement. If T4 capacity is available in your first region, set `EAST_GPU_SKU=Standard_NC4as_T4_v3` for a smaller pool. Regular nodes require suitable family and regional quota. Spot uses a separate quota and is interruptible. Quota and unrestricted SKUs do not guarantee allocation capacity. Choose regions where allocation succeeds.

## 2. Create the hub and members

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
for cluster in "$EAST" "$WEST"; do
  cluster_id=$(az aks show -g "$RG" -n "$cluster" --query id -o tsv)
  az fleet member create -g "$RG" --fleet-name "$FLEET" \
    -n "$cluster" --member-cluster-id "$cluster_id"
done
fleet_id=$(az fleet show -g "$RG" -n "$FLEET" --query id -o tsv)
object_id=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$object_id" \
  --assignee-principal-type User \
  --role 'Azure Kubernetes Fleet Manager RBAC Cluster Admin' --scope "$fleet_id"
```

The role assignment can take a few minutes to propagate. If using a service principal, use its object ID and `ServicePrincipal` instead of `User`. Run the connection block in [README section 1](README.md#1-connect) to define `hub`, `east`, and `west`.

## 3. Add a GPU pool to each member

**Choose one block**, not both. The system pools created above remain regular nodes.

Regular GPUs (use when quota and capacity are available):

```bash
for cluster in "$EAST" "$WEST"; do
  gpu_sku="$WEST_GPU_SKU"
  if [ "$cluster" = "$EAST" ]; then gpu_sku="$EAST_GPU_SKU"; fi
  az aks nodepool add -g "$RG" --cluster-name "$cluster" \
    --name gpu --mode User --node-count 1 --node-vm-size "$gpu_sku" \
    --os-sku Ubuntu --node-osdisk-size 128 --node-osdisk-type Managed --node-taints sku=gpu:NoSchedule
done
```

Spot GPUs (used for this rehearsal because regular GPU quota was unavailable):

```bash
for cluster in "$EAST" "$WEST"; do
  gpu_sku="$WEST_GPU_SKU"
  if [ "$cluster" = "$EAST" ]; then gpu_sku="$EAST_GPU_SKU"; fi
  az aks nodepool add -g "$RG" --cluster-name "$cluster" \
    --name gpu --mode User --node-count 1 --node-vm-size "$gpu_sku" \
    --os-sku Ubuntu --node-osdisk-size 128 --node-osdisk-type Managed --node-taints sku=gpu:NoSchedule \
    --priority Spot --eviction-policy Delete --spot-max-price -1 \
    --enable-cluster-autoscaler --min-count 1 --max-count 1
done
```

Install the NVIDIA device plugin; AKS provides the GPU driver with the supported GPU node image. This configuration runs the plugin only on GPU nodes and tolerates the GPU and Spot taints. Do not install a second plugin if your cluster already manages one.

```bash
east apply -k "$DEMO/manifests/device-plugin"
west apply -k "$DEMO/manifests/device-plugin"
east -n nvidia-device-plugin rollout status ds/nvidia-device-plugin-daemonset --timeout=300s
west -n nvidia-device-plugin rollout status ds/nvidia-device-plugin-daemonset --timeout=300s
east get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
west get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Do not continue without at least one allocatable GPU on each member. A DaemonSet with zero desired pods is not GPU validation.

## 4. Install Training Operator on members; only the CRD on the hub

This example uses Training Operator **v1.9.2** and `kubeflow.org/v1` **PyTorchJob**, not the newer Trainer `TrainJob` API. If the optional full Kubeflow installation already provides this operator, skip its install on that member.

```bash
east apply --server-side -k \
  'github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.9.2'
west apply --server-side -k \
  'github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.9.2'
east -n kubeflow rollout status deployment/training-operator --timeout=300s
west -n kubeflow rollout status deployment/training-operator --timeout=300s

# Copy only the CRD schema, excluding runtime metadata and status.
east get crd pytorchjobs.kubeflow.org -o json | python3 -c '
import json, sys
obj = json.load(sys.stdin)
json.dump({"apiVersion": obj["apiVersion"], "kind": obj["kind"],
           "metadata": {"name": obj["metadata"]["name"]}, "spec": obj["spec"]}, sys.stdout)
' > "$STATE/pytorchjob-crd.json"
hub apply --server-side -f "$STATE/pytorchjob-crd.json"
hub wait crd/pytorchjobs.kubeflow.org --for=condition=Established --timeout=60s
hub api-resources --api-group=placement.kubernetes-fleet.io
hub get memberclusters
```

Ensure the hub serves `ResourcePlacement` and `ClusterResourcePlacement` in `v1`. The namespace-only selector requires Fleet support; verify against your managed hub rather than assuming every Fleet version matches upstream.

Now run [README sections 2–4](README.md#2-create-the-namespace-on-both-members). Optionally install the [Kubeflow dashboard](DASHBOARD.md) on East.

References: [Azure Fleet creation](https://learn.microsoft.com/en-us/azure/kubernetes-fleet/quickstart-create-fleet-and-members), [AKS GPUs](https://learn.microsoft.com/en-us/azure/aks/use-nvidia-gpu), [AKS Spot pools](https://learn.microsoft.com/en-us/azure/aks/spot-node-pool), [Fleet v1 API](https://kubefleet.dev/docs/api-reference/placement.kubernetes-fleet.io/v1/), [Training Operator v1.9.2](https://github.com/kubeflow/training-operator/tree/v1.9.2).
