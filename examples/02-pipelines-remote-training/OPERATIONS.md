# Repeat, troubleshoot, and clean up Demo 2

[Back to the demo](README.md). Use the variables and shell helpers from [setup](SETUP.md).

## Run again

Each new run creates its own job and placement. Before a later session, [refresh the one-hour API credentials](SETUP.md#4-issue-temporary-connections), then repeat the [run command](README.md#2-run-the-pipeline).

Stopping a pipeline does not cancel its remote job. Use the cleanup commands below to remove it.

## Change the eligible cluster

After the first run finishes:

```bash
az fleet member update -g "$RG" -f "$FLEET" -n "$EAST" \
  --labels demo.kubefleet.io/gpu-worker=true -o none
az fleet member update -g "$RG" -f "$FLEET" -n "$WEST" \
  --labels demo.kubefleet.io/gpu-worker=false -o none
hub get memberclusters -L demo.kubefleet.io/gpu-worker
```

Wait until the labels show East `true` and West `false`, then repeat the [run command](README.md#2-run-the-pipeline). Each pipeline run creates a unique job and placement. Label changes are for new scheduling decisions; they do not move an already selected running job.

To restore the remote example, set East's label to `false` and West's to `true` with the same commands.

## Cleanup and troubleshooting

Use the job/placement name printed by the pipeline (`gpu-...`):

```bash
export RUN_JOB='gpu-<run-specific-name>'
hub -n pipeline-training get rp "$RUN_JOB" -o yaml
east -n pipeline-training get pytorchjob "$RUN_JOB" -o yaml
west -n pipeline-training get pytorchjob "$RUN_JOB" -o yaml
```

Only the selected member should have the job. Inspect that member's pod and events if it is pending. An unlabeled Fleet has no eligible target; a busy GPU can leave a pod pending. `HTTP 401` can indicate expired tokens: repeat the connection block, then start a new run. `HTTP 403` indicates missing permission. A failed training job fails the pipeline; it does not start the following task.

For a running pipeline, terminate it in Kubeflow first so it cannot submit more work. Then remove its placement, wait for member cleanup, and remove the hub source:

```bash
hub -n pipeline-training delete rp "$RUN_JOB"
east -n pipeline-training wait --for=delete pytorchjob/"$RUN_JOB" --timeout=180s
west -n pipeline-training wait --for=delete pytorchjob/"$RUN_JOB" --timeout=180s
hub -n pipeline-training delete pytorchjob "$RUN_JOB"
```

Stopping a pipeline or its waiter timing out leaves its Fleet objects for inspection. The training manifest also sets its own active deadline. Delete the placement as above to stop the remote work; inspect the member to confirm deletion.

After finishing all runs, revoke this example's connections:

```bash
east -n "$PROFILE" delete secret fleet-pipeline-access
hub -n pipeline-training delete serviceaccount pipeline-submitter
east -n pipeline-training delete serviceaccount pipeline-observer
west -n pipeline-training delete serviceaccount pipeline-observer
```

Deleting these service accounts invalidates their bound tokens. Repeat [setup steps 3–4](SETUP.md#3-create-the-training-namespace-and-scoped-access) when needed again. These commands leave Example 1 and the Pipelines run history intact.
