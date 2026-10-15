# Repeat, troubleshoot, and clean up Demo 4

[Back to the demo](README.md). Use the variables from [setup](SETUP.md).

## Run the example again

Every new pipeline run gets a unique job name and Blob prefix. Start a **new run**, rather than retrying a completed run or clearing a shared folder. Cached execution is disabled. Writes within one run are immutable: a retry may reuse identical content but cannot overwrite a different artifact.

Before a later session, refresh the short-lived Kubernetes API credentials:

```bash
bash "$EXAMPLE/scripts/refresh-access.sh"
```

Do not change placements during training. The waiter fails if the selected member differs from the requested target.

## Cancel or remove one run's remote work

Terminate the run in Kubeflow first so the submission task cannot create new remote work. Set the exact run ID from the run details URL or `$STATE/run.json`, then:

```bash
export RUN_ID='<pipeline-run-id>'
.venv/bin/python "$EXAMPLE/scripts/cleanup-run.py" --state "$STATE" --run-id "$RUN_ID"
```

The helper deletes the RP, waits for Fleet to remove West's job, and then removes the hub source. It retains all Blob artifacts and pipeline history. The supplied helper assumes the documented West target and `$STATE/west`; adapt the observer kubeconfig before targeting another member. It never deletes the namespace or other demo placements.

A stopped/timed-out pipeline does not itself cancel the remote job. The job has a 20-minute active deadline; explicit cleanup is still needed for its resources.

## Inspect a run

```bash
kubectl --kubeconfig "$STATE/hub" -n blob-training get rp
kubectl --kubeconfig "$STATE/west" -n blob-training get pytorchjobs,pods
# Use the job name printed by train-remotely:
export RUN_JOB='blob-<run-hash>'
kubectl --kubeconfig "$STATE/west" -n blob-training logs "$RUN_JOB-master-0" -c pytorch
```

| Symptom | Check |
| --- | --- |
| Blob authentication error | The run uses `blob-pipeline`; the pod has `azure.workload.identity/use=true`; the SA annotation and federated issuer/subject match. |
| Blob 403 | Container-scoped role assignments have propagated; inspect identity and storage network rules. Do not enable account keys as a workaround. |
| Kubernetes API 401 | Refresh `fleet-blob-access` before a new run. Blob identity and Kubernetes API credentials are different. |
| Kubernetes API 403 | Hub submitter / member observer RBAC exists in `blob-training`. |
| GPU Pending | West has a ready GPU node, NVIDIA device plugin, sufficient allocatable GPU, and matching labels/taints. Fleet does not reserve GPU capacity. |
| ImagePullBackOff | Kubelet identity has AcrPull and the compiled digest exists in your registry. |
| Checksum mismatch | Inspect the run-specific artifact; do not bypass verification. Use a new run for changed data. |
| Evaluation failed | Inspect `evaluation/metrics.json`. Publication must remain skipped. |
| No pipeline pods | Check East's CPU nodes, Istio/webhooks, and KFP deployments before debugging the new pipeline. |

## Optional quality-failure demonstration

Use a new run with a threshold below the expected nonzero error:

```bash
.venv/bin/python "$EXAMPLE/scripts/run-pipeline.py" \
  --pipeline "$STATE/pipeline.yaml" --account "$STORAGE_ACCOUNT" \
  --target "$WEST" --namespace "$PROFILE" --threshold 0.000000000001 \
  --name 'Shared data quality rejection' --output "$STATE/rejected-run.json"
```

Expected: prepare, validate, and remote training succeed; evaluation writes metrics and fails; publish is skipped. There must be no `published/result.json` for that run. The command returns an error because this is intentionally a failed run.

## Finish a session

Clean up each run's remote work as above. This keeps Blob files and pipeline history for inspection; it also keeps the storage account, registry, identities, and clusters for another run.

To revoke the temporary Fleet API access after all runs have stopped:

```bash
kubectl --kubeconfig "$STATE/east" -n "$PROFILE" delete secret fleet-blob-access --ignore-not-found
kubectl --kubeconfig "$STATE/hub" -n blob-training delete serviceaccount blob-submitter --ignore-not-found
kubectl --kubeconfig "$STATE/west" -n blob-training delete serviceaccount blob-observer --ignore-not-found
```

Before using the demo again, rerun [setup step 3](SETUP.md#3-enable-identity-and-configure-access) to restore these accounts, then refresh access.

## Delete the dedicated environment

When finished with **all** demos, follow [shared infrastructure cleanup](../../shared/SETUP.md#cleanup-shared-infrastructure). This deletes the dedicated resource group, including the shared clusters and this demo's storage, registry, and identities. Download any files you want to keep first.

If keeping the other demos, use the per-run cleanup above instead. Storage/registry charges continue while those resources exist; GPU/CPU nodes continue to incur charges while running.
