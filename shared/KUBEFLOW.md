# Kubeflow dashboard and Pipelines on East

This installation is required for Example 2 and optional for Example 1. Both use the [shared infrastructure](SETUP.md). The full Kubeflow installation below adds the familiar dashboard and Pipelines UI to **East**, for discussing the existing workflow. It takes longer and needs extra CPU capacity. Continue with Example 2 to connect a pipeline to Fleet.

If Kubeflow is already installed, jump to **Open the dashboard**. Run these commands from the repository root after [connecting](CONNECT.md) to define the environment and `east()`.

## Install Kubeflow v1.11.0

> Add Kubeflow’s web interface and supporting services to East.

Add regular CPU capacity, leaving GPU nodes for training:

```bash
az aks nodepool add -g "$RG" --cluster-name "$EAST" --name kubeflow \
  --mode User --node-count 2 --node-vm-size Standard_D8as_v5
mkdir -p .cache/bin
git clone --depth 1 --branch v1.11.0 \
  https://github.com/kubeflow/manifests.git .cache/kubeflow-manifests
python3 -m venv .venv
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
east get pods -A
east get pvc -A
```

Resolve failed workloads and unbound PVCs before presenting. The unchanged upstream example uses email `user@example.com` and password `12341234`, as documented in the release README. If you customized Dex, use your configured credentials instead. Keep the demo private and access it through the localhost tunnel below.

## Open the dashboard

> Open East’s Kubeflow interface in your browser to explore its local environment.

In a separate terminal, with the same connection setup:

```bash
east -n istio-system port-forward svc/istio-ingressgateway 8080:80 --address 127.0.0.1
```

Open **http://localhost:8080/oauth2/start**, sign in using the installed demo account, and select the user's profile. You can show the Kubeflow home page and Pipelines UI. Ctrl+C closes the tunnel.

The dedicated `gpu-training` namespace in Example 1 is not a Kubeflow user Profile. Do not expect its PyTorchJobs to appear in every dashboard view. The dashboard also cannot show West's job status automatically. Show the terminal's GPU logs and member PyTorchJob status beside the dashboard; integrating remote results into a pipeline is the [second example](../examples/02-pipelines-remote-training/README.md).

Source: [Kubeflow manifests v1.11.0](https://github.com/kubeflow/manifests/tree/v1.11.0).
