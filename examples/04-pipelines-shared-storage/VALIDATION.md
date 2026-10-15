# Validation

Local validation:

```bash
.venv/bin/python -m unittest discover -s examples/04-pipelines-shared-storage/tests -v
```

The focused tests cover artifact tampering, cross-run references, model-quality rejection, publication provenance, remote-job failure, the Fleet job/placement boundary, and the compiled five-task dependency graph.

Live validation is recorded below after running against Azure. Do not treat compilation or mocks as proof of cross-region execution.

## Azure validation — October 15, 2026

The full pipeline completed successfully at **17:45:36 UTC**. Kubeflow Pipelines ran on `demo-east`; Fleet placed the PyTorchJob on `demo-west` in West US 2.

| Check | Observed result |
| --- | --- |
| Pipeline run | `10cf127b-7379-48cf-9247-42411e9dc268`, `SUCCEEDED` |
| Workflow | `fleet-shared-blob-training-6jvms`; all five tasks succeeded |
| Remote job | `blob-6d178e648084235df48e07e8`, `Succeeded` on West |
| GPU | NVIDIA A100 80GB PCIe; CUDA 12.4 |
| Dataset | 1,024 training rows, 256 validation rows, eight features |
| Evaluation | MSE approximately `0.000339`, below the `0.02` threshold |
| Storage | Nine artifacts under this run's Blob prefix |
| Integrity | All 13 manifest/reference checks passed against the actual downloaded bytes |
| Publication | Result links the validated dataset, model, checkpoint, metrics, West member, and GPU |
| Authentication | East and West used separate federated Workload Identities for Blob; Kubernetes API access used scoped service accounts |
| RBAC | Hub submitter could create PyTorchJobs in `blob-training`; West observer could not |

West's training log included:

```text
GPU=NVIDIA A100 80GB PCIe CUDA=12.4
DATASET_SHA256=cfd36d746f10465346826179e7ac7cdf69a0a929a0af687acc2018914a8ad4c5
TRAINING_SUCCEEDED device=cuda
```

The training checksum matches the dataset prepared in East. Evaluation and publication consumed the saved West model; publication reverified the model and checkpoint bytes. The successful run and its artifacts were retained for inspection.

## Live rejection path

A second run, `15092030-593b-48b8-91c0-c5789bd7cb9d`, used a deliberately strict MSE threshold of `1e-12`:

- Prepare, validate, and remote GPU training succeeded.
- Evaluation wrote failing metrics and failed the task.
- `publish-results` was `Omitted` because its dependency did not succeed.
- No `published/result.json` existed for that run.

The intentional failure was archived in Kubeflow after inspection. Its remote work was removed with the documented cleanup helper; Blob evidence was retained.

## Local checks

Eight focused unit tests passed, including corrupted/missing artifacts, cross-run references, failed evaluation, remote training failure, and graph dependencies. Pipeline compilation, Python compilation, shell syntax, local documentation links, and `git diff --check` passed. The exported reference YAML contains placeholder registry addresses, not environment credentials or subscription details.

## Limits of this validation

This proves shared application data and model artifacts across regions, not checkpoint recovery, live migration, regional storage failover, private endpoint connectivity, automatic cancellation, or production identity integration for the Kubernetes APIs. GPU capacity was prepared in advance. Kubeflow's internal metadata/log store remained in East.
