"""Compile a pipeline that lets Fleet choose the training cluster."""
import argparse
import json
from pathlib import Path

from kfp import compiler, dsl, kubernetes
import yaml

HERE = Path(__file__).resolve().parent
JOB = yaml.safe_load((HERE.parents[1] / 'shared/manifests/pytorchjob.yaml').read_text())
PLACEMENT = yaml.safe_load((HERE / 'manifests/placement.yaml').read_text())
RUNNER = (HERE / 'scripts/remote-training.py').read_text()


@dsl.container_component
def remote_training(run_id: str, result: dsl.OutputPath(str)):
    return dsl.ContainerSpec(
        image='python:3.11-slim',
        command=['python3', '-u', '-c', RUNNER],
        args=['/fleet-access/connections.json', run_id,
              json.dumps(JOB), json.dumps(PLACEMENT), result],
    )


@dsl.container_component
def continue_pipeline(result: str):
    return dsl.ContainerSpec(
        image='python:3.11-slim',
        command=['python3', '-u', '-c',
                 'import json,sys; result=json.loads(sys.argv[1]); '
                 'assert result["state"] == "Succeeded"; '
                 'print("PIPELINE_CONTINUED after remote GPU training:", json.dumps(result))'],
        args=[result],
    )


@dsl.pipeline(name='fleet-remote-gpu-training')
def training_pipeline():
    training = remote_training(run_id=dsl.PIPELINE_JOB_ID_PLACEHOLDER)
    training.set_caching_options(False)
    training.set_retry(num_retries=0)
    training.set_cpu_request('100m').set_memory_request('128Mi')
    training.set_cpu_limit('500m').set_memory_limit('256Mi')
    kubernetes.use_secret_as_volume(training, secret_name='fleet-pipeline-access',
                                   mount_path='/fleet-access')
    following = continue_pipeline(result=training.outputs['result'])
    following.set_caching_options(False)
    following.set_cpu_request('100m').set_memory_request('64Mi')
    following.set_cpu_limit('500m').set_memory_limit('128Mi')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='.state/remote-training-pipeline.yaml')
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(training_pipeline, str(target))
    print('Compiled', target)
