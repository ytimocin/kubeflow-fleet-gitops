# Kubeflow training with Azure Fleet

Run a GPU training job on one AKS member, then use Fleet to run it in another region.

1. **[Regional placement of Kubeflow GPU training jobs](examples/01-regional-gpu-training/README.md)** — Run a training job on a GPU in East, then change its Fleet placement to run it again in West.
2. **[Kubeflow Pipelines → remote GPU training](examples/02-pipelines-remote-training/README.md)** — Start a pipeline on East, let Fleet choose an eligible GPU cluster, and continue the pipeline when training finishes.

Start with Example 1 to create the Fleet and two GPU members. Example 2 adds Kubeflow Pipelines and a submission/waiting component. Both include manual commands and explain what each step demonstrates.

Fleet places Kubernetes resources. Training Operator runs the job on the selected member. Changing regions starts a **new execution**; it does not transfer a running process, data, or checkpoints.

Despite the repository name, this demo uses explicit `az` and `kubectl` commands. Argo CD is not required.
