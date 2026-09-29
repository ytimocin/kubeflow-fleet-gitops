# Kubeflow training with Azure Fleet

Run a GPU training job on one AKS member, then use Fleet to run it in another region.

1. **[Regional placement of Kubeflow GPU training jobs](examples/01-regional-gpu-training/README.md)** — Run a training job on a GPU in East, then change its Fleet placement to run it again in West.
2. **[Kubeflow Pipelines → remote GPU training](examples/02-pipelines-remote-training/README.md)** — Start a pipeline on East, let Fleet choose an eligible GPU cluster, and continue the pipeline when training finishes.

**Choose either example; neither requires running the other.** Complete the [shared infrastructure setup](shared/SETUP.md) once to create a Fleet and two GPU members, or [connect to an existing environment](shared/CONNECT.md).

| Choose | What else is needed? |
| --- | --- |
| Example 1 | Nothing beyond shared setup |
| Example 2 | [Kubeflow Pipelines on East](shared/KUBEFLOW.md), then its own [setup](examples/02-pipelines-remote-training/SETUP.md) |

Both include manual commands and explain what each step demonstrates. They use separate training namespaces and can share the same infrastructure.

Fleet places Kubernetes resources. Training Operator runs the job on the selected member. Changing regions starts a **new execution**; it does not transfer a running process, data, or checkpoints.

Despite the repository name, this demo uses explicit `az` and `kubectl` commands. Argo CD is not required.
