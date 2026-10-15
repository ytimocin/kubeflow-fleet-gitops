# Demo 1: Run GPU training in two regions

Run one Kubeflow PyTorchJob on East’s GPU, then change its Fleet placement to run it on West’s GPU.

## Before you start

Complete [shared setup](../../shared/SETUP.md), or [connect to your existing environment](../../shared/CONNECT.md). Kubeflow Pipelines is not required. If repeating this demo, [reset the previous job](OPERATIONS.md#reset) first.

Use the same terminal, from the repository root:

```bash
export DEMO="$PWD/examples/01-regional-gpu-training"
```

## 1. Prepare the namespace

```bash
hub apply -f "$DEMO/manifests/namespace.yaml"
hub wait crp/gpu-training-namespace \
  --for=condition=ClusterResourcePlacementAvailable --timeout=180s
```

## 2. Run in East

```bash
hub create -f "$SHARED/manifests/pytorchjob.yaml"
hub create -f "$DEMO/manifests/placement.yaml"
hub -n gpu-training get resourceplacement gpu-training

east -n gpu-training wait --for=create pytorchjob/regional-gpu-training --timeout=180s
east -n gpu-training wait --for=condition=Succeeded \
  pytorchjob/regional-gpu-training --timeout=900s
east -n gpu-training logs regional-gpu-training-master-0 -c pytorch \
  | tee "$STATE/east-training.log"
west -n gpu-training get pytorchjobs
```

Expect the GPU name, decreasing loss, and `TRAINING_SUCCEEDED device=cuda`. West should have no job yet. **Check the member’s `Succeeded` condition: Fleet’s `Available=True` does not prove training success.**

## 3. Switch to West

After East succeeds, change only the placement:

```bash
hub -n gpu-training patch resourceplacement gpu-training --type=merge \
  -p '{"spec":{"policy":{"placementType":"PickFixed","clusterNames":["demo-west"]}}}'

west -n gpu-training wait --for=create pytorchjob/regional-gpu-training --timeout=300s
west -n gpu-training wait --for=condition=Succeeded \
  pytorchjob/regional-gpu-training --timeout=900s
west -n gpu-training logs regional-gpu-training-master-0 -c pytorch \
  | tee "$STATE/west-training.log"
east -n gpu-training wait --for=delete pytorchjob/regional-gpu-training --timeout=300s
east -n gpu-training wait --for=delete pod/regional-gpu-training-master-0 --timeout=180s
```

Expect successful GPU training on West and removal of the old job from East. **West starts a new execution; no running process, data, or checkpoint is transferred.** This demo selects clusters explicitly; automatic GPU-capacity selection and pipeline integration are separate work.

## Next steps

- [Open the Kubeflow dashboard](../../shared/KUBEFLOW.md) — shows East’s local Kubeflow environment.
- [Reset, troubleshoot, or clean up](OPERATIONS.md#reset).
- [Validation results](VALIDATION.md) — real A100 → T4 GPU execution verified.
- [Also available: Kubeflow Pipelines → remote training](../02-pipelines-remote-training/README.md).
