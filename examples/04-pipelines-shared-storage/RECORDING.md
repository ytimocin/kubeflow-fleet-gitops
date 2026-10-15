# Recording: East → shared data → West → East

Prepare identities, images, capacity, credentials, and Portal tabs off camera. Keep the script on the other screen. Show only the Kubeflow graph, the demo's Blob folder, and the necessary terminal commands.

## 1. Introduce the graph

Say: “This pipeline prepares and validates data in East, runs GPU training in West through Fleet, then evaluates the saved model back in East.”

Open Kubeflow → **Pipelines** and the uploaded **Fleet shared Blob storage** definition, or the run graph. Show the five tasks. The `train-remotely` pipeline component runs in East; the GPU job it submits runs in West.

## 2. Start one run

Say: “Each run gets its own storage folder. The tasks pass file references, and the data itself lives in Azure Blob Storage.”

Use the run helper from [setup](SETUP.md#5-start-the-pipeline) off camera so the password prompt is not recorded. Open its printed run link. The helper sets `blob-pipeline` as the service account. Use this same run for all remaining shots.

## 3. Show the data

Say: “The first task wrote the training and validation datasets. The second task checked their shape and checksums.”

After those tasks succeed, open Azure Portal → the demo storage account → **Data storage → Containers → fleet-demo4 → runs → this run's folder → data**. Show `train.json`, `validation.json`, and `validated.json`. The folder hash appears in the task output references.

## 4. Show Fleet placement

Say: “The pipeline submits a PyTorchJob and a ResourcePlacement to the hub. This placement explicitly targets West.”

```bash
kubectl --kubeconfig "$STATE/hub" -n blob-training get resourceplacements
```

Copy this run's `blob-...` name into `RUN_JOB` off camera.

```bash
kubectl --kubeconfig "$STATE/hub" -n blob-training get rp "$RUN_JOB" \
  -o 'custom-columns=NAME:.metadata.name,TYPE:.spec.policy.placementType,TARGET:.spec.policy.clusterNames'
```

## 5. Show GPU execution and saved model

Wait off camera for the job to finish. Say: “West downloaded the dataset from Blob Storage and trained on a real GPU. It then saved the model and checkpoint back to storage.”

```bash
kubectl --kubeconfig "$STATE/west" -n blob-training logs "$RUN_JOB-master-0" -c pytorch
```

Show `GPU=`, `DATASET_SHA256`, and `TRAINING_SUCCEEDED`. Name the GPU shown in the logs. In Portal, show this run's **training** folder: `model.json`, `checkpoint.pt`, and `manifest.json`.

## 6. Show evaluation and publication

Say: “Evaluation runs back in East. It downloads the model produced in West and tests it against the held-out validation data. Results are published only if that check passes.”

In Kubeflow, open this run → **Graph** → **evaluate-model** → **Logs**. Show `EVALUATION mse=... passed=True`. Then click **publish-results** → **Logs**, and show the result reference. In Portal, open `published/result.json` and the linked `evaluation/metrics.json`.

## 7. Close on the completed graph

Say: “Kubeflow coordinates the steps, Fleet places the training job, and Blob Storage shares the data and model across regions.”

Show all five green task checks. This demo saves a checkpoint but does not demonstrate resuming from it or live process migration. Cut provisioning, downloads, retries, and idle waiting from the recording.
