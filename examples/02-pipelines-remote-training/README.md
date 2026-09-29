# Pipelines → Fleet → GPU training

> **Run my training on a suitable GPU cluster and tell me when it finishes.**

A pipeline running on East submits a PyTorchJob and a placement to the Fleet hub. Fleet chooses one eligible member. The pipeline waits for that member's training to succeed before starting its next step.

```text
Pipeline on East → Fleet hub → eligible GPU member → training succeeds
       ↑                          │
       └──── checks job status ───┘ → next pipeline step
```

East does not hardcode West as the training destination. A platform administrator labels eligible GPU clusters; Fleet uses `PickN: 1` and label affinity to choose one. For the first run, we label only West eligible so you can see remote execution.

**“Suitable” means labeled GPU-capable in this example.** The label does not measure free GPUs or reserve capacity. Kubernetes may queue the training pod if its GPU is busy. Fleet places the resource; Training Operator and Kubernetes execute it.

## 1. Prepare the connection

> Give the pipeline permission to submit work and check its result.

Complete [SETUP.md](SETUP.md), including Kubeflow Pipelines on East. Keep its terminal variables and functions loaded.

## 2. Compile and run

> Start a two-step pipeline without choosing a destination cluster in the pipeline.

From the repository root:

```bash
.venv/bin/python "$PIPELINE_DEMO/pipeline.py" --output "$STATE/remote-training-pipeline.yaml"
```

In a separate terminal, load the [connection settings](../01-regional-gpu-training/OPERATIONS.md#connect) and keep this running:

```bash
east -n istio-system port-forward svc/istio-ingressgateway 8080:80 --address 127.0.0.1
```

Back in the first terminal:

```bash
.venv/bin/python "$PIPELINE_DEMO/scripts/run-pipeline.py" \
  --pipeline "$STATE/remote-training-pipeline.yaml" \
  --output "$STATE/remote-pipeline-run.json"
```

Enter your Kubeflow demo password when prompted. The helper uses the local demo's Dex login; it is not an enterprise SSO integration. It prints the run link and waits up to 20 minutes for completion. You can also upload the compiled YAML and start a run through **Pipelines** in the dashboard at http://127.0.0.1:8080/oauth2/start.

## 3. See the result

> Show that East's pipeline continued only after training finished on West.

```bash
hub -n pipeline-training get resourceplacements
west -n pipeline-training get pytorchjobs
```

Use the job name printed in the pipeline log:

```bash
export RUN_JOB='gpu-<run-specific-name>'
west -n pipeline-training logs "${RUN_JOB}-master-0" -c pytorch
```

Open the run in the Pipelines UI. The `remote-training` task prints the selected cluster, GPU model, and `TRAINING_SUCCEEDED device=cuda`. The `continue-pipeline` task prints `PIPELINE_CONTINUED` with the same result. Both tasks must succeed.

The wait checks the **member PyTorchJob's `Succeeded` condition and CUDA logs**. Fleet's `Available=True` alone does not establish training completion.

## 4. Optional: change the eligible cluster

> Run the same pipeline again with East eligible, without changing its code.

After the first run finishes:

```bash
az fleet member update -g "$RG" -f "$FLEET" -n "$EAST" \
  --labels demo.kubefleet.io/gpu-worker=true -o none
az fleet member update -g "$RG" -f "$FLEET" -n "$WEST" \
  --labels demo.kubefleet.io/gpu-worker=false -o none
hub get memberclusters -L demo.kubefleet.io/gpu-worker
```

Wait until the labels show East `true` and West `false`, then repeat step 2's **run** command. Each pipeline run creates a unique job and placement. Label changes are for new scheduling decisions; they do not move an already selected running job.

To restore the remote example, set East's label to `false` and West's to `true` with the same commands.

## What this adds—and what remains

This example adds a submission and result-waiting component to a real Kubeflow pipeline. The component knows the hub and has read connections to the possible members; the pipeline author does not select a member. It reuses Example 1's small synthetic GPU training job.

It does not automatically convert an existing pipeline, provide GPU capacity reservation, transfer data/checkpoints, or migrate a running process. Production integration also needs durable authentication, shared artifact storage, and cancellation/cleanup handling.

**Stopping the pipeline does not cancel its remote job.** See [cleanup and troubleshooting](SETUP.md#cleanup-and-troubleshooting). The demo's credentials are short-lived; refresh them before a later run.

[Rehearsal evidence and local tests](VALIDATION.md).
