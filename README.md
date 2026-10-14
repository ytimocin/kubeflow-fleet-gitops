# Kubeflow training with Azure Fleet

Run GPU training across AKS members, integrate it with Kubeflow Pipelines, and add a new GPU member to the Fleet.

1. **[Regional placement of Kubeflow GPU training jobs](examples/01-regional-gpu-training/README.md)** — Run a training job on a GPU in East, then change its Fleet placement to run it again in West.
2. **[Kubeflow Pipelines → remote GPU training](examples/02-pipelines-remote-training/README.md)** — Start a pipeline on East, let Fleet choose an eligible GPU cluster, and continue the pipeline when training finishes.
3. **[Add a GPU member to the Fleet](examples/03-add-gpu-member/README.md)** — Join an additional GPU-enabled AKS cluster, verify membership, and place a real CUDA training job on it.

**Choose any example; they do not require running in order.** Complete the [shared infrastructure setup](shared/SETUP.md) once to create a Fleet and two GPU members, or [connect to an existing environment](shared/CONNECT.md).

| Choose | What else is needed? |
| --- | --- |
| Example 1 | Nothing beyond shared setup |
| Example 2 | [Kubeflow Pipelines on East](shared/KUBEFLOW.md), then its own [setup](examples/02-pipelines-remote-training/SETUP.md) |
| Example 3 | [One additional AKS cluster with a working GPU](examples/03-add-gpu-member/SETUP.md); full Kubeflow is not required on it |

All three include manual commands and explain what each step demonstrates. They use separate training namespaces and can share the same infrastructure. Example 3 includes a [recording script](examples/03-add-gpu-member/RECORDING.md) with narration, commands, and Azure Portal shots; keep provisioning and waits off camera.

[Watch the recorded walkthrough of Examples 1 and 2 on YouTube](https://youtu.be/RIsdPnI-bfU).

Fleet places Kubernetes resources. Training Operator runs the job on the selected member. Changing regions starts a **new execution**; it does not transfer a running process, data, or checkpoints.

Despite the repository name, this demo uses explicit `az` and `kubectl` commands. Argo CD is not required.
