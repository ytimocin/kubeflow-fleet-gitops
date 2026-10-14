# Validation record

**Passed on October 14, 2026:** provisioned a new AKS cluster, joined it to the existing Azure Fleet, and used Fleet placement to run a real CUDA PyTorchJob on its GPU. The job completed at **18:14:51 UTC (11:14:51 AM Pacific)**.

| Check | Observed result |
| --- | --- |
| New member | `demo-gpu`, West US 2 |
| AKS | 1.35.8; one regular CPU system node and one Spot GPU node |
| GPU pool | `gpu`, `Standard_NC24ads_A100_v4` |
| Device | NVIDIA A100 80GB PCIe; one allocatable `nvidia.com/gpu` |
| Azure membership | `Succeeded` |
| Hub membership | `Joined=True`; three members joined |
| Namespace placement | `member-expansion-namespace` available; namespace created only on the new member |
| Workload placement | `new-member-training` selected only `demo-gpu` |
| Member PyTorchJob | `Succeeded`; training container exit code 0 |

Representative logs:

```text
GPU=NVIDIA A100 80GB PCIe CUDA=12.4
epoch=0 loss=31.558737
epoch=35 loss=0.000010
TRAINING_SUCCEEDED device=cuda; synthetic regression
```

The hub and member job UIDs differed. The namespace was absent from East and West, confirming the new placement did not send this workload to either original member. Training success was checked directly on the member, not inferred from Fleet availability.

## Checks

- Namespace, CRP, rendered PyTorchJob, and RP passed server-side dry-run validation against the live hub before creation.
- Training Operator v1.9.2 and NVIDIA device plugin v0.20.1 were installed on the new cluster.
- The Kustomize overlay preserved the shared PyTorchJob spec exactly, changing only name and namespace. The original workload manifest remains unchanged.
- New/updated Markdown command blocks parse in Bash and zsh; local document links, YAML, embedded training Python, and `git diff --check` pass.
- The documented job reset removed the RP first, then the member job/pod, then the hub source. The namespace and its CRP were retained for another take.
- Final checks at 11:16 AM Pacific found all three members joined with Ready nodes and one allocatable GPU each. Examples 1 and 2 retained the same resources and eligibility labels as before this rehearsal.

## Scope and limitations

This rehearsal created a fresh AKS member in an existing resource group and Fleet. It did not recreate the hub or reinstall Kubeflow on East. Full Kubeflow/Pipelines is not needed on the new member; pipeline observer credentials and eligibility were not extended to it.

The first Spot A100 VM disappeared shortly after startup, and the GPU pool returned to zero instances. Enabling the cluster autoscaler with minimum and maximum one restored a replacement node. The successful run used that replacement. The setup guide includes this configuration, but neither quota nor the autoscaler guarantees replacement Spot capacity.

Membership removal, a second join, and deletion of the AKS cluster were not exercised in this rehearsal. The new member is intentionally left joined. This demonstrates explicit `PickFixed` placement onto additional GPU capacity, not automatic free-GPU discovery, live process migration, checkpoint transfer, or a shared GPU resource pool across clusters.
