# Demo 2: Remote GPU training from a pipeline

Run a two-task Kubeflow pipeline in East. Its first task submits training through Fleet and waits for the GPU job to finish. Its second task continues with the result.

```text
East: remote-training → hub: job + placement → West: GPU job
            ↓ waits for success and reads logs
East: continue-pipeline
```

## 1. Set up once

Complete [Demo 2 setup](SETUP.md), then return here in the same terminal. It covers the shared Fleet, Kubeflow on East, member labels, and access permissions. You do not need to run Demo 1.

The placement uses **PickN: 1**: Fleet chooses one member labeled `demo.kubefleet.io/gpu-worker=true`. Setup labels only West, making the first run remote. Labels express eligibility; they do not reserve a free GPU.

## 2. Run the pipeline

Compile from the repository root:

```bash
.venv/bin/python "$PIPELINE_DEMO/pipeline.py" --output "$STATE/remote-training-pipeline.yaml"
```

In a **second terminal**, open the repository root and keep this running. If you chose a different `STATE` directory, use its `east` file instead:

```bash
kubectl --kubeconfig .state/east -n istio-system \
  port-forward svc/istio-ingressgateway 8080:80 --address 127.0.0.1
```

In the **first terminal**, submit the pipeline:

```bash
.venv/bin/python "$PIPELINE_DEMO/scripts/run-pipeline.py" \
  --pipeline "$STATE/remote-training-pipeline.yaml" \
  --namespace "$PROFILE" --output "$STATE/remote-pipeline-run.json"
```

Enter your Kubeflow password. The helper prints the run ID and waits up to 20 minutes. It supports the demo's Dex login; for a different authentication setup, use your Kubeflow UI to upload the generated YAML and create a run.

## 3. Check the result

Open **http://127.0.0.1:8080/oauth2/start**, sign in, and select your profile. Click **Pipelines → Runs**, open the run matching the printed ID, then click each task and its **Logs** tab.

| Task | Expected result |
| --- | --- |
| `remote-training` | Selected cluster, GPU name, and `TRAINING_SUCCEEDED device=cuda` |
| `continue-pipeline` | `PIPELINE_CONTINUED` with the training result |

Both tasks should succeed. To check West directly:

```bash
hub -n pipeline-training get resourceplacements
west -n pipeline-training get pytorchjobs
export RUN_JOB='gpu-<job-name-suffix-from-the-output>'
west -n pipeline-training logs "${RUN_JOB}-master-0" -c pytorch
```

The pipeline checks the member job's `Succeeded` condition and CUDA logs. Placement `Available=True` alone does not prove training completed.

This demo uses synthetic data in GPU memory and does not save a model. For shared datasets and saved models, use [Demo 4](../04-pipelines-shared-storage/README.md).

## Next steps

- [Repeat, choose a different member, troubleshoot, or clean up](OPERATIONS.md).
- [Validation results](VALIDATION.md).
- Source: [pipeline graph](pipeline.py) and [remote training component](scripts/remote-training.py).

This is a custom integration component, not automatic conversion of existing pipelines. API credentials expire and need refreshing. Stopping a pipeline does not cancel the remote job; follow the cleanup guide.
