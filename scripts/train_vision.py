"""Fine-tune a hieroglyph sign classifier on an artifact-level split and export it to ONNX.

Needs PyTorch and torchvision (not part of the server requirements):

    pip install torch torchvision pillow onnx
    python scripts/train_vision.py --data /data/MMM --source mmm --out models/sign_classifier \
        --arch resnet18 --epochs 20

The data folder uses the ImageFolder layout <label>/<file>, as in the MMM/MEH releases
(github.com/imak-ai-lab/egyptian-hieroglyph-datasets, CC BY-SA 4.0). The script:

1. builds an artifact-level train/val/test split (no monument in two splits) and saves it,
2. fine-tunes an ImageNet-pretrained backbone with augmentation suited to stone and paint
   (rotation ±10°, perspective, brightness/contrast, blur; never horizontal flips, because
   mirrored signs change reading direction),
3. calibrates the output with temperature scaling on the validation split,
4. evaluates on the untouched test split with app.vision_bench (accuracy, macro F1, ECE),
5. exports model.onnx + classes.json + model_card.json, and registers the model as a
   candidate in the model registry (promotion needs an administrator).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.vision_bench import DATASETS, artifact_split, evaluate_onnx, manifest_from_folder, report_markdown

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True)
    parser.add_argument("--source", required=True, choices=sorted(DATASETS))
    parser.add_argument("--out", required=True)
    parser.add_argument("--arch", default="resnet18", choices=["resnet18", "mobilenet_v3_small", "efficientnet_b0"])
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--artifact-pattern", default=r"^(.*?)[_\-]\d+$")
    args = parser.parse_args()

    dataset = DATASETS[args.source]
    if not dataset["benchmark_eligible"]:
        raise SystemExit(f"{dataset['name']}: licence '{dataset['license']}' does not allow benchmark use. {dataset.get('note', '')}")
    try:
        import torch
        import torchvision
        from PIL import Image
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from torchvision import transforms
    except ImportError as exc:
        raise SystemExit("Install the training extras: pip install torch torchvision pillow onnx") from exc

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items = manifest_from_folder(args.data, args.source, args.artifact_pattern)
    split = artifact_split(items)
    if split["leakage"]:
        raise SystemExit(f"Artifact leakage between splits: {split['leakage'][:5]}")
    (out / "split.json").write_text(json.dumps({k: v for k, v in split.items() if k != "splits"} | {
        "files": {name: [i["image"] for i in rows] for name, rows in split["splits"].items()}}, indent=1))
    classes = sorted({i["label"] for i in split["splits"]["train"]})
    index = {c: n for n, c in enumerate(classes)}

    train_tf = transforms.Compose([
        transforms.Grayscale(3), transforms.Resize((args.size, args.size)),
        transforms.RandomRotation(10), transforms.RandomPerspective(0.15, p=0.4),
        transforms.ColorJitter(0.4, 0.4), transforms.RandomApply([transforms.GaussianBlur(3)], p=0.3),
        transforms.ToTensor(), transforms.Normalize([0.5] * 3, [0.5] * 3)])
    eval_tf = transforms.Compose([transforms.Grayscale(3), transforms.Resize((args.size, args.size)),
                                  transforms.ToTensor(), transforms.Normalize([0.5] * 3, [0.5] * 3)])

    class Signs(Dataset):
        def __init__(self, rows, tf):
            self.rows = [r for r in rows if r["label"] in index]
            self.tf = tf

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            row = self.rows[i]
            return self.tf(Image.open(row["image"]).convert("RGB")), index[row["label"]]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = getattr(torchvision.models, args.arch)(weights="DEFAULT")
    if args.arch == "resnet18":
        model.fc = nn.Linear(model.fc.in_features, len(classes))
    else:
        model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, len(classes))
    model.to(device)
    train = DataLoader(Signs(split["splits"]["train"], train_tf), batch_size=args.batch, shuffle=True, num_workers=4)
    val = DataLoader(Signs(split["splits"]["val"], eval_tf), batch_size=args.batch)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)
    best, best_state = -1.0, None
    for epoch in range(args.epochs):
        model.train()
        for x, y in train:
            opt.zero_grad()
            loss = loss_fn(model(x.to(device)), y.to(device))
            loss.backward()
            opt.step()
        sched.step()
        model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y in val:
                correct += (model(x.to(device)).argmax(1).cpu() == y).sum().item()
                total += len(y)
        acc = correct / max(1, total)
        print(f"epoch {epoch + 1}: val top-1 {acc:.3f}")
        if acc > best:
            best, best_state = acc, {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    # temperature scaling on the validation split (Guo et al. 2017)
    model.eval()
    logits, labels = [], []
    with torch.no_grad():
        for x, y in val:
            logits.append(model(x.to(device)).cpu())
            labels.append(y)
    logits, labels = torch.cat(logits), torch.cat(labels)
    temperature = torch.ones(1, requires_grad=True)
    lbfgs = torch.optim.LBFGS([temperature], lr=0.01, max_iter=200)
    lbfgs.step(lambda: (lambda l: (l.backward(), l)[1])(nn.functional.cross_entropy(logits / temperature, labels)))

    class Calibrated(nn.Module):
        def __init__(self, inner, t):
            super().__init__()
            self.inner, self.t = inner, float(t)

        def forward(self, x):
            return torch.softmax(self.inner(x) / self.t, dim=1)

    onnx_path = out / "model.onnx"
    torch.onnx.export(Calibrated(model.cpu(), temperature.item()).eval(), torch.randn(1, 3, args.size, args.size), str(onnx_path),
                      input_names=["image"], output_names=["probabilities"], dynamic_axes={"image": {0: "batch"}})
    (out / "classes.json").write_text(json.dumps(classes, ensure_ascii=False))
    report = evaluate_onnx(onnx_path, classes, split["splits"]["test"], args.size, grayscale=False)
    card = {"name": f"sign-classifier-{args.arch}", "task": "hieroglyph sign classification", "arch": args.arch,
            "dataset": dataset, "split": split["summary"], "temperature": temperature.item(), "test": report,
            "limitations": "Trained on crops of single signs; reading a whole inscription still needs detection and ordering."}
    (out / "model_card.json").write_text(json.dumps(card, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(report_markdown(report, card["name"]))
    try:
        from app.storage.registry import register
        register(card["name"], str(onnx_path), metrics=report, dataset=args.source, license=dataset["license"], card=card)
    except Exception as exc:  # registry is optional when training offline
        print(f"Not registered: {exc}")
    print(report_markdown(report, card["name"]))


if __name__ == "__main__":
    main()
