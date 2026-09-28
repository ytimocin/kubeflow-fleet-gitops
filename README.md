# Kubeflow training with Azure Fleet

Run a GPU training job on one AKS member, then use Fleet to run it in another region.

| Example | Status |
| --- | --- |
| [1. Regional placement of Kubeflow GPU training jobs](examples/01-regional-gpu-training/README.md) | Start here |
| [2. Kubeflow Pipelines / Argo → remote GPU training](examples/02-pipelines-remote-training/README.md) | Upcoming |

The first example contains manual commands, Azure setup, GPU manifests, and optional Kubeflow dashboard setup. Two members keep the regional comparison simple; a third is optional.

Fleet places Kubernetes resources. Training Operator runs the job on the selected member. Changing regions starts a **new execution**; it does not transfer a running process, data, or checkpoints.

Despite the repository name, this demo uses explicit `az` and `kubectl` commands. Argo CD is not required.
