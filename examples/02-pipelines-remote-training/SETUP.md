# Setup: Pipelines with Fleet

Run commands from the repository root. This example uses the shared Fleet hub, two GPU members, NVIDIA device plugins, and Training Operator. You do not need to run Example 1.

## 1. Prepare East's pipeline service

> Install the interface and services that run the pipeline on East.

Complete [shared infrastructure setup](../../shared/SETUP.md), then the [Kubeflow dashboard and Pipelines installation](../../shared/KUBEFLOW.md). The full installation includes Pipelines; standalone Training Operator alone is insufficient. Skip installation if those services already exist.

Load [shared connection settings](../../shared/CONNECT.md), using **your** resource group and Fleet. Then:

```bash
export PIPELINE_DEMO="$PWD/examples/02-pipelines-remote-training"
export PROFILE=kubeflow-user-example-com
python3 -m venv .venv
.venv/bin/pip install -r "$PIPELINE_DEMO/requirements.txt"
east -n kubeflow rollout status deployment/ml-pipeline --timeout=600s
east get namespace "$PROFILE"
```

The supplied manifests use member names `demo-east` and `demo-west`. Adjust `manifests/namespace.yaml` if yours differ. The run helper defaults to the upstream demo user `user@example.com`; use `--username` and `--namespace` if customized.

## 2. Choose eligible GPU members

> Tell Fleet which clusters are allowed to run this training.

For the first run, make West the only eligible member. Azure managed Fleet requires its API for member labels:

```bash
az fleet member update -g "$RG" -f "$FLEET" -n "$EAST" \
  --labels demo.kubefleet.io/gpu-worker=false -o none
az fleet member update -g "$RG" -f "$FLEET" -n "$WEST" \
  --labels demo.kubefleet.io/gpu-worker=true -o none
hub get memberclusters -L demo.kubefleet.io/gpu-worker
```

Wait for East `false` and West `true` before running. These commands set this dedicated demo's user labels; preserve any other user labels if adapting an existing Fleet. Verify GPUs with the shared connection guide’s node checks. This label expresses eligibility, not current free GPU capacity.

## 3. Create the training namespace and scoped access

> Create a separate workspace for pipeline training and narrowly scoped permissions.

```bash
hub apply -f "$PIPELINE_DEMO/manifests/namespace.yaml"
hub wait crp/pipeline-training-namespace \
  --for=condition=ClusterResourcePlacementAvailable --timeout=180s
hub apply -f "$PIPELINE_DEMO/manifests/hub-access.yaml"
east apply -f "$PIPELINE_DEMO/manifests/member-access.yaml"
west apply -f "$PIPELINE_DEMO/manifests/member-access.yaml"
```

The hub account can create and read jobs and placements only in `pipeline-training`. Member accounts can read jobs, pods and logs only there. The CRP copies only the namespace shell; each pipeline run's RP selects its own job.

## 4. Issue temporary connections

> Let the pipeline contact the hub and read results from either possible member.

```bash
connections_file="$STATE/pipeline-connections-$(date -u +%Y%m%dT%H%M%SZ).json"
python3 "$PIPELINE_DEMO/scripts/create-connections.py" \
  --hub "$STATE/hub" \
  --member "$EAST=$STATE/east" \
  --member "$WEST=$STATE/west" \
  --output "$connections_file"
east -n "$PROFILE" create secret generic fleet-pipeline-access \
  --from-file=connections.json="$connections_file" --dry-run=client -o yaml | east apply -f -
```

The helper requests one-hour service-account tokens and writes a private file under ignored `.state/`. The pipeline receives this Secret only in its submission/waiting task; it never receives your administrator kubeconfigs. Cluster APIs must be reachable from East's pipeline pod.

Repeat this block with a new filename before credentials expire. The Kubernetes API controls the actual issued token lifetime. Access is deliberately limited for this demo; use an appropriate identity design for production.

Return to [run the pipeline](README.md#2-compile-and-run).

## Cleanup and troubleshooting

> Remove a run's remote work or diagnose why its pipeline is waiting.

Use the job/placement name printed by the pipeline (`gpu-...`):

```bash
export RUN_JOB='gpu-<run-specific-name>'
hub -n pipeline-training get rp "$RUN_JOB" -o yaml
east -n pipeline-training get pytorchjob "$RUN_JOB" -o yaml
west -n pipeline-training get pytorchjob "$RUN_JOB" -o yaml
```

Only the selected member should have the job. Inspect that member's pod and events if it is pending. An unlabeled Fleet has no eligible target; a busy GPU can leave a pod pending. `HTTP 401` can indicate expired tokens: repeat the connection block, then start a new run. `HTTP 403` indicates missing permission. A failed training job fails the pipeline; it does not start the following task.

For a completed or canceled run, remove its placement first, verify member cleanup, then remove the hub source:

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

Deleting these service accounts invalidates their bound tokens. Repeat steps 3–4 when needed again. These commands leave Example 1 and the Pipelines run history intact.
