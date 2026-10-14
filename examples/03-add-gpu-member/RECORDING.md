# Demo 3 — grow the Fleet with a GPU member

Aim for about 2–3 minutes of edited footage. Read the plain paragraphs aloud; bracketed text is an action, not narration. Commands follow the sentence they demonstrate. Keep this file on your other screen.

## Prepare off camera

Complete [SETUP.md](SETUP.md) first. Keep its terminal open with `SUBSCRIPTION`, `RG`, `FLEET`, `STATE`, `EXPANSION`, `NEW_MEMBER`, `NEW_CLUSTER_ID`, `hub`, and `newmember` defined. Do not show cluster creation, GPU allocation, credentials, or installation waits.

For the complete join story, start with two Fleet members and a separate, prepared `demo-gpu` cluster. If the third member is already joined, either use [Repeat the join shot](OPERATIONS.md#repeat-the-join-shot) before recording or start at section 3 and say “The new cluster has already joined.” Do not present an existing membership update as a new join.

Open Azure Portal in two tabs: your Fleet's **Members** page, and `demo-gpu` → **Node pools**. Hide unrelated tabs, account menus, notifications, and the Dock from the capture. Use the actual GPU model printed by the training logs.

## 1 — Show the starting point · Portal, about 20 seconds

[START RECORDING. Show the Fleet's Members page with `demo-east` and `demo-west`.]

So far, we've used two member clusters. Now I'll add another GPU-enabled Kubernetes cluster to the same Fleet.

[Switch to the `demo-gpu` AKS tab. Click Node pools, then the `gpu` pool. Point to its VM size and node count.]

I've already provisioned this AKS cluster and its GPU pool. It also has the NVIDIA device plugin and Kubeflow Training Operator, so it is ready to execute training jobs.

[Switch to the terminal.]

Kubernetes reports the GPU as allocatable on this new cluster.

```bash
clear
newmember get nodes -l kubernetes.azure.com/accelerator=nvidia \
  -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

[Hold on the GPU column showing at least 1.]

## 2 — Join the Fleet · Terminal, about 15 seconds

I'll register this cluster as a new Fleet member. Its nodes stay in their own Kubernetes cluster; Fleet coordinates placement across the members.

```bash
az fleet member create --subscription "$SUBSCRIPTION" \
  -g "$RG" --fleet-name "$FLEET" -n "$NEW_MEMBER" \
  --member-cluster-id "$NEW_CLUSTER_ID" -o none --no-wait
```

[STOP RECORDING after the command returns. No output is expected with `-o none`; the join is still asynchronous. Run these waits off camera.]

```bash
az fleet member wait --subscription "$SUBSCRIPTION" \
  -g "$RG" --fleet-name "$FLEET" --fleet-member-name "$NEW_MEMBER" \
  --created --interval 10 --timeout 900
hub wait --for=create membercluster/"$NEW_MEMBER" --timeout=300s
hub wait membercluster/"$NEW_MEMBER" --for=condition=Joined --timeout=300s
```

## 3 — Verify membership · Terminal and Portal, about 20 seconds

[START A NEW RECORDING. If starting here with an existing membership, say “The new cluster has already joined.”]

The hub now reports three joined members, including demo-gpu.

```bash
clear
hub get memberclusters
```

[Point to `demo-gpu` and `JOINED=True`. Switch to the Fleet Members page in Azure Portal and refresh.]

Azure Portal also shows the third member. Next, I'll prove it can run a GPU workload through Fleet.

[Hold briefly on the new member row, then switch to the terminal.]

## 4 — Prepare the namespace · Terminal, about 15 seconds

A ClusterResourcePlacement will create the namespace on the new member. NamespaceOnly means it copies just the namespace shell.

```bash
hub apply -f "$EXPANSION/manifests/namespace.yaml"
```

[STOP RECORDING and wait off camera.]

```bash
hub wait crp/member-expansion-namespace \
  --for=condition=ClusterResourcePlacementAvailable --timeout=180s
newmember get namespace member-expansion
```

## 5 — Place the training job · Terminal, about 25 seconds

[START A NEW RECORDING.]

A ResourcePlacement selects resources inside a namespace. Here it selects our training job, and PickFixed names demo-gpu as its destination.

```bash
clear
cat "$EXPANSION/manifests/placement.yaml"
```

[Point to `kind: PyTorchJob`, `name: new-member-training`, and `clusterNames: [demo-gpu]`.]

I'll submit the same training program used earlier, under a separate job name and namespace, then create its placement on the hub.

```bash
hub create -k "$EXPANSION/manifests/training"
hub create -f "$EXPANSION/manifests/placement.yaml"
```

[STOP RECORDING. Wait off camera; do not record image pulls or scheduling delays.]

```bash
newmember -n member-expansion wait --for=create \
  pytorchjob/new-member-training --timeout=300s
newmember -n member-expansion wait --for=condition=Succeeded \
  pytorchjob/new-member-training --timeout=900s
```

## 6 — Prove GPU training and close · Terminal, about 25 seconds

[START A NEW RECORDING.]

The training job has succeeded on the new member.

```bash
clear
newmember -n member-expansion get pytorchjob new-member-training
```

The logs identify the GPU and confirm successful CUDA execution.

```bash
newmember -n member-expansion logs new-member-training-master-0 -c pytorch
```

[Point to `GPU=...` and `TRAINING_SUCCEEDED device=cuda`. Say the actual GPU name if you want to name it.]

We've expanded the Fleet and verified that the new member can run GPU training. Placement policies still control where jobs execute; adding a member does not automatically move existing jobs.

[Hold on the success line, then STOP RECORDING.]

Optional short subtitles: “Join a prepared GPU cluster”, “Three joined members”, and “CUDA training succeeded on the new member”.
