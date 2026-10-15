#!/usr/bin/env bash
set -euo pipefail
: "${STATE:?Set STATE to the directory containing hub/east/west kubeconfigs}"
: "${WEST:?Set WEST to the Fleet member name}"
: "${PROFILE:?Set PROFILE to the Kubeflow namespace}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
connections_file="$STATE/blob-connections-$(date -u +%Y%m%dT%H%M%SZ).json"
python3 "$script_dir/create-connections.py" --hub "$STATE/hub" \
  --member "$WEST=$STATE/west" --output "$connections_file"
kubectl --kubeconfig "$STATE/east" -n "$PROFILE" create secret generic fleet-blob-access \
  --from-file="connections.json=$connections_file" --dry-run=client -o yaml |
  kubectl --kubeconfig "$STATE/east" apply -f -
