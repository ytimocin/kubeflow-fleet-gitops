# Reset, troubleshooting, and cleanup

Load the variables and `hub` / `newmember` functions from [setup](SETUP.md) before using these commands. All cleanup below is scoped to Example 3 and its dedicated AKS cluster. Stop on an error and inspect it before advancing to the next cleanup stage.

## Reset the training job

Use this between runs. Keep the namespace CRP and Fleet membership if you only want to repeat the training portion.

```bash
hub -n member-expansion delete resourceplacement new-member-training \
  --ignore-not-found --wait=true --timeout=180s
newmember -n member-expansion wait --for=delete \
  pytorchjob/new-member-training --timeout=180s
newmember -n member-expansion wait --for=delete \
  pod/new-member-training-master-0 --timeout=180s
hub -n member-expansion delete pytorchjob new-member-training \
  --ignore-not-found --wait=true --timeout=60s
hub -n member-expansion get resourceplacements,pytorchjobs
newmember -n member-expansion get pytorchjobs,pods
```

The last two commands should show no demo resources. Keep the actual GPU nodes running to run the example again; deleting a placement does not stop or delete the AKS cluster.

## Repeat member registration

First reset the training job above. Then remove this example's namespace placement and confirm member cleanup before removing membership:

```bash
hub delete crp member-expansion-namespace --ignore-not-found \
  --wait=true --timeout=180s
newmember wait --for=delete namespace/member-expansion --timeout=180s
hub delete namespace member-expansion --ignore-not-found --timeout=180s
az fleet member delete --subscription "$SUBSCRIPTION" -g "$RG" \
  --fleet-name "$FLEET" -n "$NEW_MEMBER" --yes
hub wait --for=delete membercluster/"$NEW_MEMBER" --timeout=300s
hub get memberclusters
newmember get nodes
```

Use Azure Fleet's API to remove managed membership; do not delete its MemberCluster directly. This leaves the new AKS cluster, GPU pool, device plugin, and Training Operator ready to rejoin. It removes neither East nor West. If you adapted this to an existing cluster used by other placements, inspect those dependencies before removing membership.

## Troubleshoot the relevant gate

| Gate | Check |
| --- | --- |
| GPU allocation fails | Azure node-pool error, Spot/family quota, region/SKU capacity; membership cannot fix allocation |
| Azure membership not successful | `az fleet member show --subscription "$SUBSCRIPTION" -g "$RG" -f "$FLEET" -n "$NEW_MEMBER"` |
| Azure succeeds but hub not joined | `hub get membercluster "$NEW_MEMBER" -o yaml`; inspect conditions and recent member-agent heartbeat |
| Namespace not available | `hub describe crp member-expansion-namespace`; confirm the member name matches the manifest |
| RP not applied | `hub -n member-expansion describe resourceplacement new-member-training`; check Training Operator's CRD on the member |
| Training Pending | `newmember -n member-expansion describe pod new-member-training-master-0`; inspect GPU availability, taints, and image pull |
| Job Failed | `newmember -n member-expansion logs new-member-training-master-0 -c pytorch`; reset only after investigating |

The workload tolerates the `sku=gpu` and AKS Spot taints. It needs one allocatable NVIDIA GPU. Do not remove its GPU request or CUDA assertion to make a failed demo appear successful.

## Delete the additional infrastructure when finished

First complete the reset and membership-removal procedures above. Confirm `NEW_MEMBER` identifies only the dedicated Example 3 cluster before running:

```bash
az aks show --subscription "$SUBSCRIPTION" -g "$RG" -n "$NEW_MEMBER" \
  --query '{Name:name,Region:location,ResourceGroup:resourceGroup}' -o table
az aks delete --subscription "$SUBSCRIPTION" -g "$RG" \
  -n "$NEW_MEMBER" --yes --no-wait
```

This deletes the additional AKS cluster and its managed infrastructure. Do not delete the shared resource group while the other demos are still needed. GPU nodes incur charges while allocated and Spot nodes can be evicted.
