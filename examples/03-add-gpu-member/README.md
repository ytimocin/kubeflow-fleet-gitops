# Add a GPU member to an existing Fleet

Grow an existing Fleet from two members to three, then run a real CUDA training job on the new member. The new AKS cluster joins the **Fleet**; its nodes remain part of its own Kubernetes cluster.

The walkthrough has three distinct gates: Azure membership succeeds, the hub reports `Joined=True`, and a PyTorchJob succeeds on the new member's GPU. Membership alone does not prove usable GPU capacity.

## Before you start

- Reuse the hub and two members from [shared setup](../../shared/SETUP.md), or [connect to an existing Fleet](../../shared/CONNECT.md).
- Complete [setup](SETUP.md) to provision `demo-gpu`, install its GPU device plugin and Training Operator, and define `hub` / `newmember` shell helpers. Leave it outside the Fleet until the membership step below.
- Examples 1 and 2 do not need to be running. Full Kubeflow and Pipelines are not required on the new member.
- Repeating the demo? Use [reset](OPERATIONS.md#reset-the-training-job) first. To repeat member registration, also [remove only the new membership](OPERATIONS.md#repeat-member-registration).

The supplied manifests use Fleet member name `demo-gpu` and namespace `member-expansion`. If you choose another member name, update `clusterNames` in both manifests. The AKS cluster name and Fleet member name are the same in this walkthrough.

## 1. Show the existing Fleet and the new cluster

```bash
hub get memberclusters
newmember get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Expect two joined members and at least one allocatable GPU on the separate AKS cluster. In Azure Portal, show the Fleet's **Members** page, then `demo-gpu` → **Node pools** → `gpu`. Use the actual VM SKU and GPU name from your environment; Fleet does not require identical GPUs across members.

## 2. Join the new member

The setup guide already saved the AKS resource ID in `NEW_CLUSTER_ID`.

```bash
az fleet member create --subscription "$SUBSCRIPTION" \
  -g "$RG" --fleet-name "$FLEET" -n "$NEW_MEMBER" \
  --member-cluster-id "$NEW_CLUSTER_ID" \
  -o none --no-wait
```

This requests membership; `--no-wait` does not mean joining has completed. Wait for completion:

```bash
az fleet member wait --subscription "$SUBSCRIPTION" \
  -g "$RG" --fleet-name "$FLEET" --fleet-member-name "$NEW_MEMBER" \
  --created --interval 10 --timeout 900
hub wait --for=create membercluster/"$NEW_MEMBER" --timeout=300s
hub wait membercluster/"$NEW_MEMBER" --for=condition=Joined --timeout=300s
```

Verify the joined member:

```bash
hub get memberclusters
```

Expect three rows with `JOINED=True` and recent heartbeats. Refresh the Fleet **Members** page in Azure Portal to show `demo-gpu` with successful provisioning. Azure installs/manages the Fleet member components as part of membership; do not manually install a second member agent.

## 3. Prepare a namespace on the new member

A ClusterResourcePlacement can distribute cluster-scoped resources; here it creates only the namespace shell on `demo-gpu`.

```bash
hub apply -f "$EXPANSION/manifests/namespace.yaml"
```

Wait for the namespace before creating the job:

```bash
hub wait crp/member-expansion-namespace \
  --for=condition=ClusterResourcePlacementAvailable --timeout=180s
newmember get namespace member-expansion
```

`NamespaceOnly` prevents this CRP from also distributing the namespace's workloads. A separate ResourcePlacement will select the training job.

## 4. Send training to the new member

`PickFixed` means the placement explicitly names its target. This RP selects only `new-member-training` in `member-expansion` and targets only `demo-gpu`.

```bash
cat "$EXPANSION/manifests/placement.yaml"
hub create -k "$EXPANSION/manifests/training"
hub create -f "$EXPANSION/manifests/placement.yaml"
hub -n member-expansion get resourceplacement new-member-training
```

The Kustomize overlay reuses the same [training program](../../shared/manifests/pytorchjob.yaml) as Example 1, changing only its name and namespace. It requests one GPU and asserts CUDA is available; there is no CPU fallback.

Wait for completion:

```bash
newmember -n member-expansion wait --for=create \
  pytorchjob/new-member-training --timeout=300s
newmember -n member-expansion wait --for=condition=Succeeded \
  pytorchjob/new-member-training --timeout=900s
```

## 5. Prove GPU execution

```bash
newmember -n member-expansion get pytorchjob new-member-training
newmember -n member-expansion logs new-member-training-master-0 -c pytorch \
  | tee "$STATE/new-member-training.log"
```

Expect `Succeeded`, the actual GPU name, and `TRAINING_SUCCEEDED device=cuda`. Fleet's placement availability alone is not proof of training success.

The Fleet now has a third GPU-capable member. Joining does not automatically move existing jobs or pool the GPUs into one Kubernetes cluster. Existing placement policies still determine where resources go.

## Relationship to the other demos

This example has its own namespace, CRP, RP, and job. It does not change East/West placements or their pipeline eligibility labels.

To use this new member in Example 2 later, first extend that example's namespace placement, install its member observer RBAC, and regenerate the pipeline connections Secret with an additional `--member "$NEW_MEMBER=$STATE/new-member"`. Only then mark it eligible through the Azure Fleet member API. Simply labeling a newly joined member is insufficient: the pipeline must have namespace-scoped access to read its result. See [pipeline setup](../02-pipelines-remote-training/SETUP.md).

## References

- [Azure Fleet membership](https://learn.microsoft.com/en-us/azure/kubernetes-fleet/quickstart-create-fleet-and-members#join-member-clusters)
- [AKS GPU preparation](https://learn.microsoft.com/en-us/azure/aks/use-nvidia-gpu)
- [Fleet v1 placement API](https://kubefleet.dev/docs/api-reference/placement.kubernetes-fleet.io/v1/)
- [Reset, troubleshooting, and cleanup](OPERATIONS.md)
- [Validation record](VALIDATION.md)
