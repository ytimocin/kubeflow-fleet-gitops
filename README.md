# kubeflow-fleet-gitops

GitOps source for the Kubeflow → Azure Kubernetes Fleet Manager spike (Phase 1: one AKS cluster).
`root.yaml` is an app-of-apps; `apps/` points at upstream `kubeflow/manifests@v1.11.0` (minus Katib, KServe, Spark; plus the Training Operator v1) and at `platform/` (NVIDIA device plugin, sample StatefulSet/DaemonSet).
