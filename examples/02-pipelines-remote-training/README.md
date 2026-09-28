# Upcoming: Kubeflow Pipelines / Argo → remote GPU training

**Status: planned; remote workflow integration is not implemented or validated here.**

Keep a pipeline on its existing cluster, submit a training job through the Fleet hub, wait for its result on the selected member, then continue the pipeline.

```text
Pipeline UI / SDK → Argo workflow → submission step → Fleet hub
                                                      ↓ placement
                                                remote GPU member
                                                      ↓ result
                               pipeline waits, collects output, continues
```

The integration must handle hub authentication and namespace RBAC, unique job names, retries and cancellation, member-side completion and logs, and shared dataset/checkpoint/output storage. Fleet placement availability alone does not establish training success.

Before implementing, confirm whether the customer submits through Pipelines UI/SDK, an Argo template, Training Operator APIs, or direct YAML; identify the actual training kind/version and where the workflow waits for completion. Argo Workflows and Argo CD are different components.

[Example 1](../01-regional-gpu-training/README.md) establishes the GPU placement building block. It does not yet prove that the existing pipeline can remain unchanged.
