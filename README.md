# kubeflow-fleet-gitops

Git source for the Kubeflow → Azure Kubernetes Fleet Manager spike.

- `platform/` — our own manifests on top of Kubeflow: the NVIDIA device plugin (own namespace, tolerates the AKS
  Spot taint) and sample workloads (a StatefulSet with a PVC, a DaemonSet).
- Kubeflow itself is installed the official way (`kustomize build | kubectl apply --server-side`), not from this repo.
- Phase 2 adds Argo CD pointed at the **Fleet hub**, syncing from this repo.
