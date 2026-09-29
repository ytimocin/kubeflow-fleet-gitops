# Connection, reset, and troubleshooting

[Back to the demo](README.md).

## Connect

Follow the [shared connection instructions](../../shared/CONNECT.md), then set this example's path:

```bash
export DEMO="$PWD/examples/01-regional-gpu-training"
```

## Reset

> Remove this demo’s training jobs so you can run it again while keeping the clusters and GPUs.

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

> Check where the job is stuck and what is preventing it from running.

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

> Remove the demo when finished, or delete its entire dedicated resource group to remove the infrastructure too.

To remove only the example, reset it first, then run:

```bash
hub delete crp gpu-training-namespace --wait=true
hub delete namespace gpu-training
```

To remove the Fleet and clusters used by both examples, follow [shared infrastructure cleanup](../../shared/SETUP.md#cleanup-shared-infrastructure).
