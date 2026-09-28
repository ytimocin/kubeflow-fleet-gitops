# Rehearsal record

**Passed on 2026-09-28:** Fleet placed the GPU PyTorchJob on East, then a placement change created a distinct successful execution on West and removed the old job and pod from East.

| Member | Region | GPU pool | CUDA device reported | PyTorchJob |
| --- | --- | --- | --- | --- |
| demo-east | East US 2 | Spot `Standard_NC24ads_A100_v4` | NVIDIA A100 80GB PCIe | Succeeded at 22:43:43 UTC |
| demo-west | West US 2 | Spot `Standard_NC4as_T4_v3` | Tesla T4 | Succeeded at 22:44:05 UTC |

Both pods completed with exit code 0, used CUDA 12.4, and printed `TRAINING_SUCCEEDED device=cuda`. The member job UIDs differed, confirming separate executions.

Representative logs:

```text
East: GPU=NVIDIA A100 80GB PCIe CUDA=12.4
      epoch=0 loss=31.558737
      epoch=35 loss=0.000010
      TRAINING_SUCCEEDED device=cuda; synthetic regression

West: GPU=Tesla T4 CUDA=12.4
      epoch=0 loss=31.521517
      epoch=35 loss=0.000011
      TRAINING_SUCCEEDED device=cuda; synthetic regression
```

Also verified:

- Both managed Fleet members joined; the namespace-only CRP created the namespace on both.
- Training Operator v1.9.2 ran on both members. PyTorchJob and ResourcePlacement passed hub server-side validation.
- East ran AKS 1.35.8; West ran AKS 1.35.7. NVIDIA device plugin v0.20.1 exposed one GPU per member.
- Image: `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime`.
- The existing Kubeflow v1.11.0 dashboard on East returned HTTP 200 after authentication.
- Documentation links, Bash/zsh syntax, YAML parsing, embedded Python syntax, and AKS webhook exclusions in the rendered Kubeflow configuration passed checks.

Observed limitation: while East's training pod was Pending, the top-level RP reported `ResourcePlacementAvailable=True / ResourceAvailable`. Its per-cluster condition reported `NotAllWorkAreAvailabilityTrackable`; the Work's PyTorchJob condition reported `Available=True / NotTrackable`. Training success was therefore checked directly on each member.

East T4 Spot allocation attempts failed. An A100 Spot pool allocated successfully; West's T4 pool used an ephemeral OS disk, while the setup guide explicitly selects managed OS disks to reduce allocation constraints. Regular GPU quota was unavailable. Spot capacity can be evicted and this record does not guarantee availability at the next rehearsal.

This revision reused the prepared Fleet and AKS members; it did not recreate a fresh resource group. The optional full Kubeflow install was previously rehearsed on East, while the standalone Training Operator install was applied to West. The remote Pipelines/Argo integration remains upcoming.
