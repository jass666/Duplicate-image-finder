#!/usr/bin/env python3
"""Train and use a simple image-example classifier.

The immediate child folder under --train-root is the label. Deeper folders such
as "Collection Bin" are treated as organization only. Training writes a model
folder; classification is preview-only unless --apply is supplied.
"""
import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DEFAULT_MODEL = "ViT-B-32"
DEFAULT_PRETRAINED = "laion2b_s34b_b79k"


def image_files(root):
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in EXTS]


def load_clip(model_name, pretrained):
    try:
        import open_clip
        import torch
    except ImportError as e:
        raise SystemExit("Missing packages. Run run_image_organizer.bat and install the required packages.") from e
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    return torch, model.to(device).eval(), preprocess, device


def embed(paths, torch, model, preprocess, device, batch_size=32):
    vectors, good, skipped = [], [], []
    started = time.time()
    for i in range(0, len(paths), batch_size):
        batch_paths = paths[i:i + batch_size]
        ims, valid = [], []
        for p in batch_paths:
            try:
                with Image.open(p) as im:
                    ims.append(preprocess(im.convert("RGB")))
                valid.append(p)
            except Exception as e:
                skipped.append((p, str(e)))
        if ims:
            with torch.no_grad():
                x = torch.stack(ims).to(device)
                out = model.encode_image(x)
                out = out / out.norm(dim=-1, keepdim=True)
                vectors.append(out.cpu().numpy().astype("float32"))
                good.extend(valid)
        done = min(i + len(batch_paths), len(paths))
        print(f"  Encoded {done}/{len(paths)} images", end="\r", flush=True)
    print(f"\n  Finished in {time.time() - started:.1f}s")
    return (np.concatenate(vectors) if vectors else np.empty((0, 1), dtype="float32"), good, skipped)


def prototypes(embeddings, labels):
    names = sorted(set(labels))
    centers = []
    for name in names:
        c = embeddings[np.array(labels) == name].mean(axis=0)
        c /= max(np.linalg.norm(c), 1e-12)
        centers.append(c)
    return names, np.asarray(centers, dtype="float32")


def evaluate(embeddings, labels, seed=42):
    rng = np.random.default_rng(seed)
    train, test = [], []
    for name in sorted(set(labels)):
        ix = np.flatnonzero(np.array(labels) == name)
        rng.shuffle(ix)
        cut = max(1, int(len(ix) * 0.2)) if len(ix) >= 5 else 1
        test.extend(ix[:cut])
        train.extend(ix[cut:])
    if not test or not train:
        return {"tested": 0, "correct": 0, "accuracy": None}
    names, centers = prototypes(embeddings[train], [labels[i] for i in train])
    scores = embeddings[test] @ centers.T
    predicted = [names[i] for i in scores.argmax(axis=1)]
    correct = sum(p == labels[i] for p, i in zip(predicted, test))
    return {"tested": len(test), "correct": correct, "accuracy": correct / len(test), "classes": names}


def train(args):
    root = Path(args.train_root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Training folder does not exist: {root}")
    categories = [p for p in root.iterdir() if p.is_dir()]
    paths, labels = [], []
    for category in sorted(categories, key=lambda p: p.name.lower()):
        found = image_files(category)
        paths.extend(found)
        labels.extend([category.name] * len(found))
        print(f"  {category.name}: {len(found)} image(s)")
    if not paths:
        raise SystemExit("No supported images found under the training folder.")
    print(f"Found {len(paths)} image(s) in {len(categories)} top-level categories.")
    torch, model, preprocess, device = load_clip(args.model, args.pretrained)
    print(f"Model ready on {device}. Building image examples...")
    embeddings, good_paths, skipped = embed(paths, torch, model, preprocess, device, args.batch_size)
    good_labels = [labels[paths.index(p)] for p in good_paths]
    if len(set(good_labels)) < 2:
        raise SystemExit("At least two categories with readable images are required.")
    out = Path(args.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "embeddings.npy", embeddings)
    with open(out / "labels.json", "w", encoding="utf-8") as f:
        json.dump(good_labels, f, indent=2, ensure_ascii=False)
    with open(out / "paths.json", "w", encoding="utf-8") as f:
        json.dump([str(p) for p in good_paths], f, indent=2, ensure_ascii=False)
    report = evaluate(embeddings, good_labels)
    metadata = {"train_root": str(root), "model": args.model, "pretrained": args.pretrained,
                "device": device, "images": len(good_paths), "skipped": len(skipped),
                "validation": report}
    with open(out / "model.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    with open(out / "training_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["label", "path"])
        w.writerows(zip(good_labels, good_paths))
    print(f"\nSaved trained examples to: {out}")
    print(f"Validation: {report['correct']}/{report['tested']} correct" if report["tested"] else "Validation unavailable")
    if skipped:
        print(f"Skipped unreadable images: {len(skipped)}")


def classify(args):
    model_dir = Path(args.model_dir).expanduser().resolve()
    root = Path(args.input).expanduser().resolve()
    if not model_dir.is_dir():
        raise SystemExit(f"Model folder does not exist: {model_dir}")
    if not root.is_dir():
        raise SystemExit(f"Input folder does not exist: {root}")
    with open(model_dir / "model.json", encoding="utf-8") as f: meta = json.load(f)
    with open(model_dir / "labels.json", encoding="utf-8") as f: labels = json.load(f)
    with open(model_dir / "paths.json", encoding="utf-8") as f: train_paths = json.load(f)
    train_embeddings = np.load(model_dir / "embeddings.npy")
    names, centers = prototypes(train_embeddings, labels)
    paths = image_files(root)
    if not paths:
        raise SystemExit("No supported images found in the input folder.")
    torch, model, preprocess, device = load_clip(meta["model"], meta["pretrained"])
    print(f"Classifying {len(paths)} image(s) on {device}...")
    embeddings, good_paths, skipped = embed(paths, torch, model, preprocess, device, args.batch_size)
    scores = embeddings @ centers.T
    output = Path(args.output).expanduser().resolve() if args.output else root.parent / f"{root.name}_classified"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for p, s in zip(good_paths, scores):
        order = np.argsort(s)[::-1]
        best, second = float(s[order[0]]), float(s[order[1]]) if len(order) > 1 else -1.0
        label = names[order[0]] if best >= args.min_score and best - second >= args.min_margin else "Review"
        dest = output / label / p.name
        rows.append([str(p), label, best, best - second, str(dest)])
        if args.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
    with open(output / "classification_preview.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["source", "prediction", "score", "margin", "destination"]); w.writerows(rows)
    counts = {}
    for r in rows: counts[r[1]] = counts.get(r[1], 0) + 1
    print("\nResults:")
    for name in names + ["Review"]:
        if counts.get(name): print(f"  {name}: {counts[name]}")
    print(f"Preview: {output / 'classification_preview.csv'}")
    print("Nothing was copied. Add --apply to create classified copies." if not args.apply else f"Copies written to: {output}")


def main():
    ap = argparse.ArgumentParser(description="Learn image categories from labeled folders and classify new images.")
    sub = ap.add_subparsers(dest="command", required=True)
    tr = sub.add_parser("train", help="build an example-based model from top-level folders")
    tr.add_argument("train_root"); tr.add_argument("--output", default="trained_models/showroom")
    tr.add_argument("--model", default=DEFAULT_MODEL); tr.add_argument("--pretrained", default=DEFAULT_PRETRAINED)
    tr.add_argument("--batch-size", type=int, default=32); tr.set_defaults(func=train)
    cl = sub.add_parser("classify", help="classify a new image folder")
    cl.add_argument("input"); cl.add_argument("--model-dir", default="trained_models/showroom")
    cl.add_argument("--output"); cl.add_argument("--min-score", type=float, default=0.35)
    cl.add_argument("--min-margin", type=float, default=0.05); cl.add_argument("--batch-size", type=int, default=32)
    cl.add_argument("--apply", action="store_true", help="copy results; default is preview only")
    cl.set_defaults(func=classify)
    args = ap.parse_args(); args.func(args)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nStopped."); sys.exit(1)
