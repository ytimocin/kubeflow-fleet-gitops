#!/usr/bin/env bash
set -euo pipefail
: "${SUBSCRIPTION:?Set SUBSCRIPTION explicitly}"
: "${REGISTRY:?Set REGISTRY to your ACR name}"
: "${STATE:?Set STATE}"
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_tag="${IMAGE_TAG:-demo4-$(date -u +%Y%m%d%H%M%S)}"
for kind in cpu gpu; do
  base_image=python:3.11-slim
  if [ "$kind" = gpu ]; then base_image=pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime; fi
  az acr build --subscription "$SUBSCRIPTION" -r "$REGISTRY" \
    -t "demo4/$kind:$image_tag" --build-arg "BASE_IMAGE=$base_image" "$example_dir" -o none
 done
registry_server="$(az acr show --subscription "$SUBSCRIPTION" -n "$REGISTRY" --query loginServer -o tsv)"
cpu_digest="$(az acr repository show --subscription "$SUBSCRIPTION" -n "$REGISTRY" --image "demo4/cpu:$image_tag" --query digest -o tsv)"
gpu_digest="$(az acr repository show --subscription "$SUBSCRIPTION" -n "$REGISTRY" --image "demo4/gpu:$image_tag" --query digest -o tsv)"
mkdir -p "$STATE"
.venv/bin/python "$example_dir/pipeline.py" \
  --cpu-image "$registry_server/demo4/cpu@$cpu_digest" \
  --gpu-image "$registry_server/demo4/gpu@$gpu_digest" --output "$STATE/pipeline.yaml"
