# Kubeflow dashboard and Pipelines on East

Required for **demos 2 and 4**. Demos 1 and 3 only need Training Operator.

Follow [shared setup](SETUP.md) first, then [connect](CONNECT.md). Run from the repository root in the same terminal. This installs Kubeflow **v1.11.0** on East with two extra CPU nodes.

## 1. Check what is installed

```bash
az aks nodepool list -g "$RG" --cluster-name "$EAST" \
  --query '[].{Pool:name,Nodes:count,Size:vmSize,State:provisioningState}' -o table
east get nodes -l kubernetes.azure.com/agentpool=kubeflow
east -n kubeflow get deployments
east get namespace kubeflow-user-example-com --ignore-not-found
```

If only `training-operator` is present, continue with installation: Pipelines is still missing. If `ml-pipeline` and `centraldashboard` already exist, check their rollout status and the user namespace before skipping to [Open the dashboard](#3-open-the-dashboard). For a partial installation, resume the remaining steps below.

## 2. Install Kubeflow

Add CPU capacity. If the `kubeflow` pool already exists, skip creation and confirm its two nodes are Ready:

```bash
az aks nodepool add -g "$RG" --cluster-name "$EAST" --name kubeflow \
  --mode User --node-count 2 --node-vm-size Standard_D8as_v5
```

Prepare local tools. If the clone already exists, check `git -C .cache/kubeflow-manifests describe --tags --exact-match` reports `v1.11.0` and skip cloning.

```bash
mkdir -p .cache/bin
git clone --depth 1 --branch v1.11.0 \
  https://github.com/kubeflow/manifests.git .cache/kubeflow-manifests
python3.11 -m venv .venv
.venv/bin/pip install PyYAML==6.0.3
```

Use the Kubeflow release's Kustomize 5.7.1. These download commands support macOS and Linux on Intel/AMD or ARM:

```bash
os=$(uname -s | tr '[:upper:]' '[:lower:]')
arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
curl --fail --location \
  "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.7.1/kustomize_v5.7.1_${os}_${arch}.tar.gz" \
  -o .cache/kustomize.tar.gz
tar -xzf .cache/kustomize.tar.gz -C .cache/bin kustomize
.cache/bin/kustomize version
```

Enable the legacy Training Operator alongside the release's default Trainer. Keep all other upstream components:

```bash
mkdir -p .cache/kubeflow-manifests/example-gpu
python3 - <<'PY'
from pathlib import Path
root = Path('.cache/kubeflow-manifests')
text = (root / 'example/kustomization.yaml').read_text()
text = text.replace('# - ../applications/training-operator/upstream/overlays/kubeflow',
                    '- ../applications/training-operator/upstream/overlays/kubeflow')
(root / 'example-gpu/kustomization.yaml').write_text(text)
PY
.cache/bin/kustomize build .cache/kubeflow-manifests/example-gpu \
  > "$STATE/kubeflow.yaml"
```

The small helper below preserves AKS webhook namespace exclusions and controller-owned webhook fields. It prevents repeated server-side-apply conflicts without forcing ownership. Initial applies can fail while CRDs and webhooks become ready; retry up to 15 times, checking the printed errors:

```bash
applied=false
for attempt in $(seq 1 15); do
  .venv/bin/python "$SHARED/scripts/prepare-kubeflow-for-aks.py" \
    "$STATE/kubeflow.yaml" --kubeconfig "$STATE/east" || break
  if east apply --server-side -f "$STATE/kubeflow.yaml"; then
    applied=true
    break
  fi
  sleep 20
done
[ "$applied" = true ] || { echo 'Kubeflow installation did not complete'; false; }
east -n kubeflow rollout status deployment/centraldashboard --timeout=600s
east -n kubeflow rollout status deployment/training-operator --timeout=300s
east -n kubeflow rollout status deployment/ml-pipeline --timeout=600s
east -n kubeflow rollout status deployment/profiles-deployment --timeout=600s
east -n kubeflow rollout status deployment/workflow-controller --timeout=600s
east -n auth rollout status deployment/dex --timeout=300s
east -n oauth2-proxy rollout status deployment/oauth2-proxy --timeout=300s
east wait --for=create namespace/kubeflow-user-example-com --timeout=300s
east get pods -A
east get pvc -A
```

Continue only when these deployments are ready and their PVCs are bound. The unchanged upstream example uses email `user@example.com` and password `12341234`, as documented in the release README. If you customized Dex, use your configured credentials instead. Keep the demo private and access it through the localhost tunnel below.

## 3. Open the dashboard

In a **second terminal**, open the repository root. Use your actual `STATE` path if it differs from `.state`:

```bash
kubectl --kubeconfig .state/east -n istio-system \
  port-forward svc/istio-ingressgateway 8080:80 --address 127.0.0.1
```

Open **http://localhost:8080/oauth2/start**, sign in, and select `kubeflow-user-example-com`. Click **Pipelines** for pipeline definitions and runs. Keep the terminal running; Ctrl+C closes the tunnel.

This dashboard shows East. A remote West job appears through the pipeline component's logs, not as a local East job. Demo 1's `gpu-training` namespace is also separate from the user profile.

Continue with [Demo 2](../examples/02-pipelines-remote-training/README.md) or [Demo 4](../examples/04-pipelines-shared-storage/README.md).

Source: [Kubeflow manifests v1.11.0](https://github.com/kubeflow/manifests/tree/v1.11.0).
