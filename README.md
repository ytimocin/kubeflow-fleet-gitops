# Kubeflow training with Azure Fleet

Run GPU training across AKS members, integrate it with Kubeflow Pipelines, and add a new GPU member to the Fleet.

- **[Demo 1: Regional placement of Kubeflow GPU training jobs](examples/01-regional-gpu-training/README.md)** — Run a training job on East, then run it again in West.
- **[Demo 2: Kubeflow Pipelines → remote GPU training](examples/02-pipelines-remote-training/README.md)** — Start a pipeline on East, let Fleet choose an eligible GPU cluster, and continue when training finishes.
- **[Demo 3: Add a GPU member to the Fleet](examples/03-add-gpu-member/README.md)** — Join a GPU-enabled AKS cluster and run training on it.
- **[Demo 4: Multi-step pipeline with shared Azure Blob Storage](examples/04-pipelines-shared-storage/README.md)** — Prepare data in East, train in West, then evaluate and publish results in East.

**Choose any example; they do not require running in order.** Complete the [shared infrastructure setup](shared/SETUP.md) once, or [connect to an existing environment](shared/CONNECT.md).

| Choose | What else is needed? |
| --- | --- |
| Example 1 | Nothing beyond shared setup |
| Example 2 | [Kubeflow Pipelines on East](shared/KUBEFLOW.md), then its own [setup](examples/02-pipelines-remote-training/SETUP.md) |
| Example 3 | [One additional AKS cluster with a working GPU](examples/03-add-gpu-member/SETUP.md) |
| Example 4 | Kubeflow Pipelines on East, Blob Storage, Workload Identity, and its own [setup](examples/04-pipelines-shared-storage/SETUP.md) |

All four include commands and use separate training namespaces. They can share the same infrastructure.

Fleet places Kubernetes resources. Training Operator runs the job on the selected member. Changing regions starts a **new execution**; it does not transfer a running process, data, or checkpoints. Example 4 explicitly shares datasets and saves model/checkpoint files through Blob Storage; checkpoint resumption is not implemented.

Despite the repository name, this demo uses explicit `az` and `kubectl` commands. Argo CD is not required.
