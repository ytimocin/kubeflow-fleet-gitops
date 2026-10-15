"""CPU pipeline tasks; large data crosses regions through Blob, not KFP parameters."""
import argparse
import json
from pathlib import Path
import numpy as np
from storage import Store, run_prefix


def arrays(data):
    x, y = np.asarray(data['x'], dtype=np.float32), np.asarray(data['y'], dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != 8 or y.shape != (len(x), 1) or len(x) == 0:
        raise ValueError('Expected nonempty samples with eight features and one target')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Non-finite dataset values')
    return x, y


def prepare(store, run_id):
    prefix = run_prefix(run_id)
    rng = np.random.default_rng(7)
    x = rng.normal(size=(1280, 8)).astype(np.float32)
    y = x @ np.arange(1, 9, dtype=np.float32).reshape(8, 1) / 8 + 0.3
    y += rng.normal(scale=0.02, size=y.shape).astype(np.float32)
    refs = {}
    for name, indices in [('train', slice(0, 1024)), ('validation', slice(1024, None))]:
        refs[name] = store.put_json(prefix + f'data/{name}.json', {
            'x': x[indices].tolist(), 'y': y[indices].tolist()})
    return store.put_json(prefix + 'data/manifest.json', {
        'run_id': run_id, 'prefix': prefix, 'datasets': refs})


def validate(store, run_id, dataset_ref):
    prefix = run_prefix(run_id)
    manifest = store.get_json(dataset_ref, prefix)
    if manifest['run_id'] != run_id or manifest['prefix'] != prefix:
        raise ValueError('Dataset run identity mismatch')
    counts = {}
    for name in ['train', 'validation']:
        x, _ = arrays(store.get_json(manifest['datasets'][name], prefix))
        counts[name] = len(x)
    return store.put_json(prefix + 'data/validated.json', {
        **manifest, 'rows': counts, 'validated': True})


def evaluate(store, run_id, validated_ref, training_result, threshold):
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('Quality threshold must be finite and positive')
    prefix = run_prefix(run_id)
    validated = store.get_json(validated_ref, prefix)
    training = store.get_json(training_result['manifest'], prefix)
    if training['run_id'] != run_id or training['validated_dataset'] != validated_ref:
        raise ValueError('Training used a different dataset or run')
    model = store.get_json(training['model'], prefix)
    x, y = arrays(store.get_json(validated['datasets']['validation'], prefix))
    weights = np.asarray(model['weights'], dtype=np.float32)
    if weights.shape != (8, 1):
        raise ValueError('Invalid model shape')
    mse = float(np.mean((x @ weights + float(model['bias']) - y) ** 2))
    if not np.isfinite(mse):
        raise ValueError('Non-finite model evaluation')
    metrics = {'run_id': run_id, 'mse': mse, 'threshold': threshold,
               'passed': mse <= threshold, 'training': training_result,
               'validated_dataset': validated_ref}
    ref = store.put_json(prefix + 'evaluation/metrics.json', metrics)
    print(f'EVALUATION mse={mse:.6f} threshold={threshold} passed={metrics["passed"]}', flush=True)
    if not metrics['passed']:
        raise ValueError('Model quality gate failed; results will not be published')
    return ref


def publish(store, run_id, metrics_ref):
    prefix = run_prefix(run_id)
    metrics = store.get_json(metrics_ref, prefix)
    if metrics['run_id'] != run_id or metrics['passed'] is not True:
        raise ValueError('Only a passing evaluation from this run may be published')
    training = store.get_json(metrics['training']['manifest'], prefix)
    # Recheck the files before publishing a pointer to them.
    store.get(training['model'], prefix)
    store.get(training['checkpoint'], prefix)
    result = {'run_id': run_id, 'model': training['model'], 'checkpoint': training['checkpoint'],
              'dataset': metrics['validated_dataset'], 'metrics': metrics_ref,
              'training_cluster': metrics['training']['cluster'], 'gpu': training['gpu'],
              'status': 'Published'}
    return store.put_json(prefix + 'published/result.json', result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('task', choices=['prepare', 'validate', 'evaluate', 'publish'])
    for name in ['account', 'container', 'run-id', 'output']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--input', default='{}')
    p.add_argument('--training', default='{}')
    p.add_argument('--threshold', type=float, default=0.02)
    a = p.parse_args()
    store = Store(a.account, a.container)
    value = json.loads(a.input)
    if a.task == 'prepare': result = prepare(store, a.run_id)
    elif a.task == 'validate': result = validate(store, a.run_id, value)
    elif a.task == 'evaluate': result = evaluate(store, a.run_id, value, json.loads(a.training), a.threshold)
    else: result = publish(store, a.run_id, value)
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result))
    print(a.task.upper() + '_SUCCEEDED ' + json.dumps(result), flush=True)


if __name__ == '__main__': main()
