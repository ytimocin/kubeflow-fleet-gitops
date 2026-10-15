"""Compile five tasks sharing Blob artifacts across East and a Fleet GPU member."""
import argparse
from pathlib import Path
from kfp import compiler, dsl, kubernetes


def build(cpu_image, gpu_image):
    @dsl.container_component
    def prepare_data(account: str, container: str, run_id: str, result: dsl.OutputPath(str)):
        return dsl.ContainerSpec(image=cpu_image, command=['python', '/app/tasks.py', 'prepare'],
            args=['--account', account, '--container', container, '--run-id', run_id, '--output', result])

    @dsl.container_component
    def validate_data(account: str, container: str, run_id: str, dataset: str, result: dsl.OutputPath(str)):
        return dsl.ContainerSpec(image=cpu_image, command=['python', '/app/tasks.py', 'validate'],
            args=['--account', account, '--container', container, '--run-id', run_id,
                  '--input', dataset, '--output', result])

    @dsl.container_component
    def train_remotely(account: str, container: str, run_id: str, validated: str, target: str,
                       result: dsl.OutputPath(str)):
        return dsl.ContainerSpec(image=cpu_image, command=['python', '/app/remote.py'],
            args=['--account', account, '--container', container, '--run-id', run_id,
                  '--validated', validated, '--target', target, '--image', gpu_image, '--output', result])

    @dsl.container_component
    def evaluate_model(account: str, container: str, run_id: str, validated: str, training: str,
                       threshold: float, result: dsl.OutputPath(str)):
        return dsl.ContainerSpec(image=cpu_image, command=['python', '/app/tasks.py', 'evaluate'],
            args=['--account', account, '--container', container, '--run-id', run_id,
                  '--input', validated, '--training', training, '--threshold', threshold, '--output', result])

    @dsl.container_component
    def publish_results(account: str, container: str, run_id: str, metrics: str, result: dsl.OutputPath(str)):
        return dsl.ContainerSpec(image=cpu_image, command=['python', '/app/tasks.py', 'publish'],
            args=['--account', account, '--container', container, '--run-id', run_id,
                  '--input', metrics, '--output', result])

    @dsl.pipeline(name='fleet-shared-blob-training')
    def pipeline(storage_account: str, container: str = 'fleet-demo4',
                 target_member: str = 'demo-west', mse_threshold: float = 0.02):
        run_id = dsl.PIPELINE_JOB_ID_PLACEHOLDER
        prepare = prepare_data(account=storage_account, container=container, run_id=run_id)
        validate = validate_data(account=storage_account, container=container, run_id=run_id,
                                 dataset=prepare.outputs['result'])
        train = train_remotely(account=storage_account, container=container, run_id=run_id,
                               validated=validate.outputs['result'], target=target_member)
        evaluate = evaluate_model(account=storage_account, container=container, run_id=run_id,
                                   validated=validate.outputs['result'], training=train.outputs['result'],
                                   threshold=mse_threshold)
        publish = publish_results(account=storage_account, container=container, run_id=run_id,
                                   metrics=evaluate.outputs['result'])
        for task in [prepare, validate, train, evaluate, publish]:
            task.set_caching_options(False)
            task.set_retry(num_retries=0)
            task.set_cpu_request('100m').set_cpu_limit('1')
            task.set_memory_request('128Mi').set_memory_limit('512Mi')
            kubernetes.add_pod_label(task, 'azure.workload.identity/use', 'true')
            kubernetes.add_pod_annotation(task, 'sidecar.istio.io/inject', 'false')
        kubernetes.use_secret_as_volume(train, secret_name='fleet-blob-access', mount_path='/fleet-access')
    return pipeline


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu-image', required=True)
    p.add_argument('--gpu-image', required=True)
    p.add_argument('--output', default='.state/demo4/pipeline.yaml')
    a = p.parse_args()
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(build(a.cpu_image, a.gpu_image), str(out))
    print(out)
