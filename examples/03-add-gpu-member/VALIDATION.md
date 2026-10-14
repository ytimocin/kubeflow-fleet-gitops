# Validation record

Live validation is in progress on October 14, 2026. The new AKS cluster and Training Operator are provisioned. Its first Spot A100 VM disappeared shortly after startup; replacement capacity is being provisioned with cluster autoscaler minimum and maximum set to one. Successful GPU training is not yet claimed.

Local checks passed:

- The training overlay renders with `kubectl kustomize` and preserves the shared PyTorchJob spec exactly, changing only name and namespace.
- All new Markdown Bash command blocks parse in both Bash and zsh.
- Manifest YAML and the embedded training Python parse successfully.
- `git diff --check` passes.

The PR remains a draft until Azure membership, hub `Joined=True`, actual CUDA training, and reset behavior have been verified. Full Kubeflow/Pipelines is intentionally not installed on the new member.
