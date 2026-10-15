# Setup: Pipelines with Fleet

First complete [shared setup](../../shared/SETUP.md) and [Kubeflow installation](../../shared/KUBEFLOW.md), or reuse an environment with both. You do not need to run Demo 1.

## 1. Connect and prepare local tools

Load [connection settings](../../shared/CONNECT.md), then run the following from the repository root in the same terminal:

```bash
east -n kubeflow get deployment ml-pipeline
```

**If `ml-pipeline` is not found, install [Kubeflow](../../shared/KUBEFLOW.md) before continuing.** Training Operator alone is not enough.

Install the Python dependencies and check readiness:

```bash
export PIPELINE_DEMO="$PWD/examples/02-pipelines-remote-training"
export PROFILE=kubeflow-user-example-com
python3.11 -m venv .venv
.venv/bin/pip install -r "$PIPELINE_DEMO/requirements.txt"
east -n kubeflow rollout status deployment/ml-pipeline --timeout=600s
east get namespace "$PROFILE"
```

The supplied manifests use member names `demo-east` and `demo-west`. Adjust `manifests/namespace.yaml` if yours differ. The run helper defaults to the upstream demo user `user@example.com`; use `--username` and `--namespace` if customized.

## 2. Choose eligible GPU members

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

Return to [run the pipeline](README.md#2-run-the-pipeline).

[Cleanup and troubleshooting](OPERATIONS.md).
