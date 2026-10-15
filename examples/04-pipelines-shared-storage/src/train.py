"""Real CUDA training on a Fleet member, with durable model and checkpoint artifacts."""
import argparse
import io
import json
import torch
from storage import Store, run_prefix
from tasks import arrays


def main():
    p = argparse.ArgumentParser()
    for name in ['account', 'container', 'run-id', 'validated']:
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError('A real CUDA GPU is required; there is no CPU fallback')
    store, prefix = Store(a.account, a.container), run_prefix(a.run_id)
    validated_ref = json.loads(a.validated)
    validated = store.get_json(validated_ref, prefix)
    if validated['run_id'] != a.run_id or validated['validated'] is not True:
        raise ValueError('Expected validated data from this run')
    x, y = arrays(store.get_json(validated['datasets']['train'], prefix))
    gpu = torch.cuda.get_device_name(0)
    print(f'GPU={gpu} CUDA={torch.version.cuda}', flush=True)
    print('DATASET_SHA256=' + validated['datasets']['train']['sha256'], flush=True)
    torch.manual_seed(7)
    x, y = torch.tensor(x, device='cuda'), torch.tensor(y, device='cuda')
    model = torch.nn.Linear(8, 1).cuda()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    for epoch in range(80):
        optimizer.zero_grad()
        loss = torch.nn.functional.mse_loss(model(x), y)
        loss.backward()
        optimizer.step()
        if epoch % 20 == 0: print(f'epoch={epoch + 1} loss={loss.item():.6f}', flush=True)
    torch.cuda.synchronize()
    if not torch.isfinite(loss) or loss.item() >= 0.02:
        raise RuntimeError('Training did not converge')
    model_ref = store.put_json(prefix + 'training/model.json', {
        'weights': model.weight.detach().cpu().numpy().T.tolist(),
        'bias': model.bias.detach().cpu().item()})
    checkpoint = io.BytesIO()
    torch.save({'epoch': 80, 'model_state_dict': {k: v.cpu() for k, v in model.state_dict().items()},
                'optimizer_state_dict': optimizer.state_dict(), 'run_id': a.run_id}, checkpoint)
    checkpoint_ref = store.put(prefix + 'training/checkpoint.pt', checkpoint.getvalue())
    manifest = store.put_json(prefix + 'training/manifest.json', {
        'run_id': a.run_id, 'validated_dataset': validated_ref, 'model': model_ref,
        'checkpoint': checkpoint_ref, 'gpu': gpu, 'cuda': torch.version.cuda,
        'epochs': 80, 'training_loss': loss.item()})
    print('TRAINING_SUCCEEDED device=cuda', flush=True)
    print('TRAINING_RESULT ' + json.dumps(manifest), flush=True)


if __name__ == '__main__': main()
