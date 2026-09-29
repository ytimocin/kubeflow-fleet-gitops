# Rehearsal evidence

Validated on September 28, 2026 (Pacific time), using the existing rehearsal Fleet and AKS members. This validation did not provision a fresh resource group or reinstall all of Kubeflow.

| Same compiled pipeline | Fleet-selected member | Training device | Outcome |
| --- | --- | --- | --- |
| Only West labeled eligible | `demo-west` | Tesla T4, CUDA 12.4 | Remote training succeeded; following pipeline step succeeded |
| Only East labeled eligible | `demo-east` | NVIDIA A100 80GB PCIe, CUDA 12.4 | Training succeeded; following pipeline step succeeded |

Run IDs in East's Pipelines UI:

- West: `55bf1e21-294b-41e8-99b2-26de7ed96f5a`
- East: `03175b65-2edc-43c0-b103-f77cdb4f08f7`

The compiled pipeline and its arguments were unchanged between runs. Only administrator-managed member eligibility labels changed. Each run created a different PyTorchJob and ResourcePlacement. Both used `PickN: 1`; neither named a destination in the pipeline.

The waiting component read the actual member job's `Succeeded` condition, captured `GPU=...` and `TRAINING_SUCCEEDED device=cuda`, and passed a result to the next component. Its log printed `PIPELINE_CONTINUED` with the selected member and GPU evidence.

## Checks

- KFP 2.15 SDK pipeline compilation and real KFP 2.15 backend execution on East.
- Namespace-scoped service-account credentials worked on the hub and both members; reads of secrets in `default` returned HTTP 403 on all three.
- Nine unit tests cover stale placement status, ambiguous selection, pending and failed training, missing member access, missing CUDA evidence, successful result, foreign object collision, and unresolved run ID.
- Bash/zsh syntax checks for documented command blocks, local document links, YAML parsing, Python compilation, and `git diff --check`.

Run the local completion-gate tests:

```bash
python3 -m unittest discover -s examples/02-pipelines-remote-training/tests -v
```

This proves label-based placement plus pipeline result integration. It does not prove automatic free-GPU discovery, capacity reservation, production authentication, cancellation propagation, shared datasets/artifacts, or distributed training.
