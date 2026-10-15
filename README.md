# Kubeflow GPU demos with Azure Fleet

Run training across AKS clusters using Azure Kubernetes Fleet Manager. These four examples show placement, pipeline integration, adding GPU capacity, and sharing data between regions.

## Choose a demo

| Demo | What you will do | Extra setup |
| --- | --- | --- |
| [1. Run training in two regions](examples/01-regional-gpu-training/README.md) | Run a PyTorch job in East, then run it again in West | None |
| [2. Run remote training from a pipeline](examples/02-pipelines-remote-training/README.md) | Start a pipeline in East, train on a Fleet-selected member, then continue the pipeline | Kubeflow on East |
| [3. Add a GPU member](examples/03-add-gpu-member/README.md) | Join another AKS cluster and run training on its GPU | One additional GPU cluster |
| [4. Share data through Blob Storage](examples/04-pipelines-shared-storage/README.md) | Prepare data in East, train in West, then evaluate and publish in East | Kubeflow on East, Blob Storage, and ACR |

Run any demo independently. Each uses its own training namespace; all can reuse the same Fleet.

## Start here

```bash
git clone https://github.com/ytimocin/kubeflow-fleet-gitops.git
cd kubeflow-fleet-gitops
```

1. **New environment:** follow [shared setup](shared/SETUP.md) to create the Fleet and GPU members.
2. **Existing environment:** follow [connect](shared/CONNECT.md) to load credentials and check prerequisites.
3. Open your chosen demo above. For demos 2 and 4, first [install Kubeflow on East](shared/KUBEFLOW.md).

Use **Bash or zsh**, run commands from this repository's root, and keep the same terminal open. Replace values in `<angle brackets>` with your own. If a command fails, fix it before continuing. A new terminal needs the [connection setup](shared/CONNECT.md) again.

## How it works

- The **hub** stores job definitions and placement rules.
- **Fleet** copies the selected resources to member clusters.
- **Training Operator** runs each PyTorchJob on the member's GPU.
- **Kubeflow Pipelines**, used in demos 2 and 4, coordinates tasks and waits for the remote job's result.

A **ClusterResourcePlacement (CRP)** places cluster-scoped resources; these demos use it to create namespaces. A **ResourcePlacement (RP)** places selected resources within a namespace, such as a training job.

Changing a job's target starts a new execution. It does not move a running process or resume a checkpoint. Demo 4 shares data and saves checkpoints through Blob Storage, but does not implement checkpoint resumption. These examples use `az` and `kubectl`; Argo CD is not required.

## When finished

Each demo links to its cleanup commands. To delete the entire dedicated environment, use [shared cleanup](shared/SETUP.md#cleanup-shared-infrastructure). Azure resources incur charges while they exist or run; deleting a training job does not delete its GPU nodes.
