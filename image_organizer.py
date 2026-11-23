#!/usr/bin/env python3
"""
image_organizer.py (v3.0) - one tool that sorts images into folders by what they show,
then removes duplicates inside each folder, and records everything in one Excel sheet.
Nothing is ever deleted. One log, one undo.

How it works
  1. SORT   an image-understanding model (CLIP, runs locally) compares every image with the
            descriptions you gave each folder. Optional keyword rules and a tiny-image filter run too.
  2. DEDUPE inside each folder, near-identical images (perceptual hash) are found; the best one
            stays, the copies go to a 'copies' subfolder of that folder.
  3. RECORD one Excel sheet (organizer_data.xlsx) + one log (moves_log.csv) in the master folder.

What gets sorted, and how, is defined by a PROFILE (a small JSON file in the 'profiles' folder next
to this script). Create and edit profiles from the menu - no coding needed.

Install:  pip install open_clip_torch torch pillow numpy openpyxl imagehash
(the first run downloads the model, roughly 600 MB, once)

Guided (any folder):      python image_organizer.py
Command line:
  python image_organizer.py "D:\\photos"                       # preview only, moves nothing
  python image_organizer.py "D:\\photos" --apply --yes         # sort + dedupe and move
  python image_organizer.py "D:\\photos" --profile invoices    # use another profile
  python image_organizer.py --edit-profile [name]              # open the profile editor
  python image_organizer.py --list-profiles
  python image_organizer.py --undo --master "E:\\photos_organized"
"""
import argparse
import copy
import csv
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

VERSION = "3.0"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
SCRIPT_DIR = Path(__file__).resolve().parent
PROFILES_DIR = SCRIPT_DIR / "profiles"
LOG_NAME = "moves_log.csv"
XLSX_NAME = "organizer_data.xlsx"
PREVIEW_NAME = "organizer_preview.xlsx"
PROFILE_COPY = "profile_used.json"
OUT_SUFFIX = "_organized"
SEPARATE_DIR = "_duplicates"
BAD_CHARS = set('\\/:*?"<>|')

# What a new profile gets for "things that are none of your folders". They give the model
# somewhere to put unrelated images, so those land in the unsorted folder instead of being forced in.
GENERIC_OTHER = [
    "a person or a group of people",
    "a building or a street",
    "a screenshot, a document or a page of text",
    "a poster, banner or advertisement with text",
    "a logo of some other company",
    "a landscape, a road or the sky",
    "a plain background, a pattern or some other object",
]

BASE_SETTINGS = {
    "include_subfolders": True,
    "unsorted_name": "Unsorted",
    "prompt_template": "a photo of {}",
    "category_weight": 6,   # each folder counts this much in total, however many descriptions it has
    "other_weight": 8,      # the 'something else' group counts this much in total
    "thresholds": {"min_score": 0.50, "review_below": 0.75, "min_margin": 0.25, "unsorted_floor": 0.20},
    "filters": {"min_width": 0, "min_height": 0},
    "duplicates": {"enabled": True, "threshold": 6, "hash_size": 8, "copies": "inside",
                   "copies_folder": "copies"},
    "model": {"name": "ViT-B-32", "pretrained": "laion2b_s34b_b79k"},
}

DEFAULT_PROFILE = {
    "name": "Dealership brands",
    "categories": [
        {"name": "Bajaj", "keywords": [], "descriptions": [
            "a Bajaj logo",
            "the word Bajaj on a signboard or banner",
            "a Bajaj auto rickshaw, a three-wheeler",
            "a Bajaj Maxima cargo three-wheeler",
            "a Bajaj GoGo electric three-wheeler",
            "a Bajaj three-wheeler showroom"]},
        {"name": "Royal Enfield", "keywords": [], "descriptions": [
            "a Royal Enfield logo",
            "the words Royal Enfield on a signboard or banner",
            "a Royal Enfield Bullet motorcycle",
            "a Royal Enfield Classic 350 cruiser motorcycle",
            "a Royal Enfield Himalayan adventure motorcycle",
            "a Royal Enfield motorcycle showroom"]},
        {"name": "Tata", "keywords": [], "descriptions": [
            "a Tata Motors logo",
            "the word Tata on a signboard or banner",
            "a Tata Ace small commercial vehicle mini truck",
            "a Tata Intra pickup truck",
            "a Tata heavy commercial truck",
            "a Tata commercial vehicle showroom"]},
    ],
    "other_descriptions": GENERIC_OTHER + [
        "a Honda, Hero, TVS or Suzuki motorcycle or scooter",
        "a Mahindra, Ashok Leyland, Eicher or Force commercial vehicle",
        "a passenger car such as a Maruti, Hyundai or Toyota",
        "a bus or a train",
    ],
}


# =========================================================================== profiles
def with_defaults(p):
    """Fill every missing setting from BASE_SETTINGS (so older/shorter profile files still work)."""
    p = copy.deepcopy(p)
    for k, v in BASE_SETTINGS.items():
        if isinstance(v, dict):
            cur = p.get(k) if isinstance(p.get(k), dict) else {}
            p[k] = {**v, **cur}
        else:
            p.setdefault(k, v)
    p.setdefault("name", "Unnamed profile")
    p.setdefault("categories", [])
    p.setdefault("other_descriptions", list(GENERIC_OTHER))
    for c in p["categories"]:
        c.setdefault("descriptions", [])
        c.setdefault("keywords", [])
    return p


def validate(p):
    """List of problems (empty = fine)."""
    bad, cats = [], p["categories"]
    unsorted = p["unsorted_name"]
    reserved = {unsorted.lower(), p["duplicates"]["copies_folder"].lower(), SEPARATE_DIR.lower()}
    if not cats:
        bad.append("The profile has no folders yet.")
    seen = set()
    for c in cats:
        n = c["name"].strip()
        if not n or any(ch in BAD_CHARS for ch in n) or n.endswith("."):
            bad.append(f"Folder name not allowed on Windows: '{c['name']}'")
        if n.lower() in seen:
            bad.append(f"Two folders are called '{n}'.")
        if n.lower() in reserved:
            bad.append(f"'{n}' is reserved (unsorted / copies folder name).")
        seen.add(n.lower())
    if "{}" not in p["prompt_template"]:
        bad.append("prompt_template must contain {} where the description goes.")
    t = p["thresholds"]
    for k in ("min_score", "review_below", "min_margin", "unsorted_floor"):
        if not 0 <= float(t[k]) <= 1:
            bad.append(f"threshold {k} must be between 0 and 1.")
    if p["duplicates"]["copies"] not in ("inside", "separate"):
        bad.append("duplicates.copies must be 'inside' or 'separate'.")
    return bad


def load_profile(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            p = with_defaults(json.load(fh))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"Cannot read profile {path}: {e}")
    problems = validate(p)
    if problems:
        sys.exit(f"Profile {path.name} has problems:\n  - " + "\n  - ".join(problems))
    return p


def save_profile(p, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2, ensure_ascii=False)


def ensure_default_profile():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if not list(PROFILES_DIR.glob("*.json")):
        save_profile(with_defaults(DEFAULT_PROFILE), PROFILES_DIR / "dealership_brands.json")


def list_profiles():
    ensure_default_profile()
    return sorted(PROFILES_DIR.glob("*.json"))


def resolve_profile(arg):
    """--profile value: a file path, or a name inside the profiles folder."""
    if not arg:
        return list_profiles()[0]
    for cand in (Path(arg), PROFILES_DIR / arg, PROFILES_DIR / f"{arg}.json"):
        if cand.is_file():
            return cand.resolve()
    sys.exit(f"Profile not found: {arg}. Available: {', '.join(p.stem for p in list_profiles())}")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "profile"


# =========================================================================== helpers
def fmt_dur(sec):
    sec = int(round(max(sec, 0)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def progress(label, done, total, t0):
    el = time.time() - t0
    eta = el / done * (total - done) if done else 0
    sys.stdout.write(f"\r  {label}: {done}/{total}  {done / max(total, 1):5.0%}  "
                     f"elapsed {fmt_dur(el)}  left {fmt_dur(eta)}   ")
    sys.stdout.flush()


def norm(p):
    return os.path.normcase(os.path.abspath(str(p)))


def default_master(roots) -> Path:
    if len(roots) == 1:
        r = roots[0]
        if r.parent == r:
            return r / OUT_SUFFIX
        return r.parent / f"{r.name}{OUT_SUFFIX}"
    try:
        base = Path(os.path.commonpath([str(r) for r in roots]))
    except ValueError:
        base = roots[0].parent
    return base / f"multi_{len(roots)}_folders{OUT_SUFFIX}"


def normalize_roots(paths, recursive):
    uniq, seen = [], set()
    for p in paths:
        if norm(p) not in seen:
            seen.add(norm(p))
            uniq.append(p)
    if not recursive:
        return uniq, []
    keep, notes = [], []
    for r in uniq:
        parent = next((o for o in uniq if o is not r and
                       norm(r).startswith(norm(o).rstrip(os.sep) + os.sep)), None)
        if parent is None:
            keep.append(r)
        else:
            notes.append(f"{r} is inside {parent} (already included)")
    return keep, notes


def scan(roots, master, recursive=True):
    seen, found = set(), []
    skip = norm(master)
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            if recursive:
                dirnames[:] = [d for d in dirnames if norm(os.path.join(dirpath, d)) != skip]
            else:
                dirnames[:] = []
            for f in filenames:
                if Path(f).suffix.lower() in EXTS:
                    p = Path(dirpath) / f
                    if norm(p) not in seen:
                        seen.add(norm(p))
                        found.append((root, p))
    return found


def unique_dest(folder: Path, name: str, reserved: set) -> Path:
    stem, suf = Path(name).stem, Path(name).suffix
    dest, i = folder / name, 0
    while dest.exists() or norm(dest) in reserved:
        i += 1
        dest = folder / f"{stem}_{i}{suf}"
    reserved.add(norm(dest))
    return dest


def prune_empty(d: Path, stop: Path):
    try:
        while d != stop and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    except OSError:
        pass


def load_image(path):
    """(RGB image, (w, h), error). Transparent logos are put on white, otherwise a transparent
    PNG logo turns into black on black."""
    try:
        with Image.open(path) as im:
            size = im.size
            if im.format == "JPEG":
                im.draft("RGB", (640, 640))
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                bg.alpha_composite(rgba)
                return bg.convert("RGB"), size, None
            return im.convert("RGB"), size, None
    except Exception as e:
        return None, None, str(e)


# =========================================================================== step 1: sort
class Classifier:
    """Scores images against every folder's descriptions and the 'something else' group (CLIP)."""

    def __init__(self, profile):
        import open_clip
        import torch
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        m = profile["model"]
        model, _, preprocess = open_clip.create_model_and_transforms(m["name"], pretrained=m["pretrained"])
        self.model, self.preprocess = model.to(self.device).eval(), preprocess
        tokenizer = open_clip.get_tokenizer(m["name"])

        cats = profile["categories"]
        self.names = [c["name"] for c in cats]
        self.labels, owner, weights = [], [], []
        for k, c in enumerate(cats):
            ds = c["descriptions"] or [c["name"]]
            for d in ds:
                self.labels.append(d)
                owner.append(k)
                weights.append(profile["category_weight"] / len(ds))
        oth = profile["other_descriptions"]
        for d in oth:
            self.labels.append(d)
            owner.append(-1)
            weights.append(profile["other_weight"] / len(oth))
        self.owner = np.array(owner)
        self.log_w = torch.log(torch.tensor(weights, dtype=torch.float32, device=self.device))
        tpl = profile["prompt_template"]
        with torch.no_grad():
            t = self.model.encode_text(tokenizer([tpl.replace("{}", d) for d in self.labels]).to(self.device))
            self.text = t / t.norm(dim=-1, keepdim=True)
        # This is inference-only; detach before converting the learned scalar to a Python float.
        self.scale = self.model.logit_scale.exp().detach().item() if hasattr(self.model, "logit_scale") else 100.0

    def probs(self, pil_images):
        torch = self.torch
        x = torch.stack([self.preprocess(im) for im in pil_images]).to(self.device)
        with torch.no_grad():
            f = self.model.encode_image(x)
            f = f / f.norm(dim=-1, keepdim=True)
            return (self.scale * f @ self.text.T + self.log_w).softmax(dim=-1).cpu().numpy()


def folder_scores(probs, owner, n):
    cats = np.stack([probs[:, owner == k].sum(axis=1) for k in range(n)], axis=1)
    return cats, probs[:, owner == -1].sum(axis=1)


def decide(scores, names, prof, w, h, rel_text):
    """One image -> dict(folder, top, margin, by, reason, review)."""
    th, flt, unsorted = prof["thresholds"], prof["filters"], prof["unsorted_name"]
    order = np.argsort(scores)[::-1]
    top = int(order[0])
    sec = int(order[1]) if len(order) > 1 else None
    conf = float(scores[top])
    margin = conf - float(scores[sec]) if sec is not None else conf
    out = {"top": conf, "margin": margin}

    if w < flt["min_width"] or h < flt["min_height"]:
        return {**out, "folder": unsorted, "by": "Size filter", "reason": f"too small ({w}x{h})", "review": False}

    hits = []
    low = rel_text.lower()
    for k, c in enumerate(prof["categories"]):
        kw = next((x for x in c["keywords"] if x.strip() and x.strip().lower() in low), None)
        if kw:
            hits.append((k, kw))
    reasons = []
    if len(hits) == 1:
        k, kw = hits[0]
        if conf >= th["min_score"] and top != k:
            reasons.append(f"AI says {names[top]} ({conf:.0%})")
        return {**out, "folder": names[k], "by": f"Keyword '{kw}'", "reason": "; ".join(reasons),
                "review": bool(reasons)}
    if len(hits) > 1:
        reasons.append("keywords match " + " and ".join(names[k] for k, _ in hits))

    if conf >= th["min_score"]:
        folder = names[top]
        if conf < th["review_below"]:
            reasons.append(f"low confidence ({conf:.0%})")
        if sec is not None and margin < th["min_margin"]:
            reasons.append(f"close to {names[sec]} ({float(scores[sec]):.0%})")
    else:
        folder = unsorted
        if conf >= th["unsorted_floor"]:
            reasons.append(f"weak {names[top]} signal ({conf:.0%})")
    return {**out, "folder": folder, "by": "AI", "reason": "; ".join(reasons), "review": bool(reasons)}


def classify_all(clf, files, prof, batch_size):
    recs, skipped = [], []
    total, done, t0 = len(files), 0, time.time()
    n = len(clf.names)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i in range(0, total, batch_size):
            chunk = files[i:i + batch_size]
            loaded = list(ex.map(lambda rp: load_image(rp[1]), chunk))
            imgs, meta = [], []
            for (root, p), (img, size, err) in zip(chunk, loaded):
                if img is None:
                    skipped.append((p, err))
                else:
                    imgs.append(img)
                    meta.append((root, p, size))
            if imgs:
                probs = clf.probs(imgs)
                sc, other = folder_scores(probs, clf.owner, n)
                for j, (root, p, size) in enumerate(meta):
                    try:
                        rel = str(p.relative_to(root))
                    except ValueError:
                        rel = p.name
                    d = decide(sc[j], clf.names, prof, size[0], size[1], rel)
                    try:
                        st = p.stat()
                        kb, mtime = st.st_size / 1024, datetime.fromtimestamp(st.st_mtime)
                    except OSError:
                        kb, mtime = None, None
                    recs.append({
                        "path": p, "name": p.name, "w": size[0], "h": size[1], "kb": kb, "mtime": mtime,
                        "scores": [float(v) for v in sc[j]], "other": float(other[j]),
                        "best": clf.labels[int(probs[j].argmax())],
                        "dup": "Not checked", "dup_of": None, "dist": None, "dest": None, "status": "", **d})
            done += len(chunk)
            progress("Sorting", done, total, t0)
    sys.stdout.write("\n")
    return recs, skipped


# =========================================================================== step 2: dedupe
def phash_of(path, size):
    import imagehash
    try:
        with Image.open(path) as im:
            if im.format == "JPEG":
                im.draft("L", (256, 256))
            return imagehash.phash(im, hash_size=size).hash.flatten()
    except Exception:
        return None


def mark_duplicates(recs, d):
    """Per folder: keep the best image of each look-alike group, mark the rest as copies.
    Best = highest resolution, then biggest file, then oldest, then shortest path. Each copy is
    compared with the original only, so chains of slowly changing images do not merge."""
    t0, total = time.time(), len(recs)
    hashes = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i in range(0, total, 64):
            hashes += list(ex.map(lambda r: phash_of(r["path"], d["hash_size"]), recs[i:i + 64]))
            progress("Checking duplicates", min(i + 64, total), total, t0)
    sys.stdout.write("\n")
    by_folder = {}
    for r, h in zip(recs, hashes):
        r["dup"] = "Unique"
        if h is not None:
            by_folder.setdefault(r["folder"], []).append((r, h))
    for items in by_folder.values():
        H = np.array([h for _, h in items], dtype=bool)
        order = sorted(range(len(items)), key=lambda i: (
            -(items[i][0]["w"] * items[i][0]["h"]), -(items[i][0]["kb"] or 0),
            items[i][0]["mtime"].timestamp() if items[i][0]["mtime"] else 0, len(str(items[i][0]["path"]))))
        assigned = np.zeros(len(items), dtype=bool)
        for i in order:
            if assigned[i]:
                continue
            assigned[i] = True
            dist = (H != H[i]).sum(axis=1)
            hits = np.where((dist <= d["threshold"]) & ~assigned)[0]
            for j in hits:
                assigned[j] = True
                items[j][0].update(dup="Copy", dup_of=items[i][0], dist=int(dist[j]))
            if len(hits):
                items[i][0]["dup"] = "Original"


# =========================================================================== moves, log, undo
def plan_destinations(recs, master, prof):
    d = prof["duplicates"]
    reserved_main, reserved_copy = set(), set()
    for r in recs:  # kept images first, so they get the clean file names
        if r["dup"] != "Copy":
            r["dest"] = unique_dest(master / r["folder"], r["name"], reserved_main)
    for r in recs:
        if r["dup"] == "Copy":
            cdir = (master / r["folder"] / d["copies_folder"]) if d["copies"] == "inside" \
                else (master / SEPARATE_DIR / r["folder"])
            r["dest"] = unique_dest(cdir, r["name"], reserved_copy)
    for r in recs:
        r["status"] = "Planned"


def apply_moves(recs, master, folders):
    for f in folders:
        (master / f).mkdir(parents=True, exist_ok=True)
    log = master / LOG_NAME
    new = not log.exists()
    moved = failed = 0
    with open(log, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["original_path", "moved_to", "folder", "duplicate_status", "duplicate_of", "top_score"])
        for r in recs:
            try:
                r["dest"].parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(r["path"]), str(r["dest"]))
                w.writerow([str(r["path"]), str(r["dest"]), r["folder"], r["dup"],
                            str(r["dup_of"]["dest"]) if r["dup_of"] else "", f"{r['top']:.4f}"])
                fh.flush()  # logged at once, so undo works even if the run is interrupted
                r["status"] = "Moved"
                moved += 1
            except OSError as e:
                r["status"] = f"Failed: {e}"
                failed += 1
    return moved, failed


def undo(master: Path):
    log = master / LOG_NAME
    if not log.exists():
        sys.exit(f"No log found at {log}")
    with open(log, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    restored = 0
    for r in reversed(rows):
        src, dst = Path(r["moved_to"]), Path(r["original_path"])
        if src.exists() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                restored += 1
                prune_empty(src.parent, master)
            except OSError as e:
                print(f"skip (could not move back: {e}): {src}")
        else:
            print(f"skip (missing source or destination taken): {src}")
    for d in master.iterdir():
        if d.is_dir():
            prune_empty(d, master)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log.rename(master / f"moves_log_undone_{stamp}.csv")  # so a re-run starts clean
    print(f"Restored {restored} file(s). The sheet stays in {master}.")


# =========================================================================== Excel
def write_xlsx(path, recs, skipped, prof, roots, master, moved):
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as L

    names = [c["name"] for c in prof["categories"]]
    folders = names + [prof["unsorted_name"]]
    font, bold = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
    head_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", start_color="305496")
    wb = Workbook()

    ws = wb.active
    ws.title = "Data"
    heads = (["Original path", "Final path", "File name", "Width", "Height", "Megapixels", "Size (KB)",
              "Modified", "Folder"] + [f"{n} score" for n in names] +
             ["Other score", "Top score", "Margin", "Best match", "Decided by", "Needs review",
              "Review reason", "Duplicate status", "Duplicate of", "Hash distance", "Status"])
    ws.append(heads)
    col = {h: i + 1 for i, h in enumerate(heads)}
    for r in recs:
        row = ws.max_row + 1
        final = str(r["dest"]) if r["status"] in ("Planned", "Moved") else ""
        ws.append([str(r["path"]), final, r["name"], r["w"], r["h"], f"=ROUND(D{row}*E{row}/1000000,2)",
                   r["kb"], r["mtime"], r["folder"]] + r["scores"] +
                  [r["other"], r["top"], r["margin"], r["best"], r["by"], "Yes" if r["review"] else "No",
                   r["reason"], r["dup"], str(r["dup_of"]["dest"]) if r["dup_of"] else "", r["dist"], r["status"]])
    last = max(ws.max_row, 2)
    for c in ws[1]:
        c.font, c.fill = head_font, head_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2, max_row=last):
        for c in row:
            c.font = font
    for h in [f"{n} score" for n in names] + ["Other score", "Top score", "Margin"]:
        for row in range(2, last + 1):
            ws.cell(row=row, column=col[h]).number_format = "0.0%"
    for row in range(2, last + 1):
        ws.cell(row=row, column=col["Size (KB)"]).number_format = "#,##0.0"
        ws.cell(row=row, column=col["Modified"]).number_format = "yyyy-mm-dd hh:mm"
        ws.cell(row=row, column=col["Megapixels"]).number_format = "0.00"
    widths = {"Original path": 60, "Final path": 60, "File name": 28, "Best match": 44, "Review reason": 34,
              "Modified": 17, "Status": 12, "Folder": 16, "Decided by": 18, "Duplicate of": 50,
              "Duplicate status": 14}
    for h, i in col.items():
        ws.column_dimensions[L(i)].width = widths.get(h, 12)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{L(len(heads))}{last}"
    rev = L(col["Needs review"])
    ws.conditional_formatting.add(
        f"A2:{L(len(heads))}{last}",
        FormulaRule(formula=[f'${rev}2="Yes"'], fill=PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")))

    # Summary: live formulas on the Data sheet
    sm = wb.create_sheet("Summary")
    sm["A1"] = "Organizer summary"
    sm["A1"].font = Font(name="Arial", size=12, bold=True)
    sm.append([])
    sm.append(["Folder", "Images", "Kept", "Copies", "Share", "Needs review"])
    for c in sm[3]:
        c.font, c.fill = head_font, head_fill
    fl, dl = L(col["Folder"]), L(col["Duplicate status"])
    first, total_row = 4, 4 + len(folders)
    rng = lambda c: f"Data!${c}$2:${c}${last}"
    for i, f in enumerate(folders):
        r = first + i
        sm.append([f, f"=COUNTIF({rng(fl)},A{r})", f"=B{r}-D{r}",
                   f'=COUNTIFS({rng(fl)},A{r},{rng(dl)},"Copy")',
                   f"=IF($B${total_row}=0,0,B{r}/$B${total_row})",
                   f'=COUNTIFS({rng(fl)},A{r},{rng(rev)},"Yes")'])
    sm.append(["Total"] + [f"=SUM({c}{first}:{c}{total_row - 1})" for c in "BCDEF"])
    for row in sm.iter_rows(min_row=4, max_row=total_row):
        for c in row:
            c.font = bold if row[0].value == "Total" else font
        row[4].number_format = "0.0%"
    sm.column_dimensions["A"].width = 20
    for c in "BCDEF":
        sm.column_dimensions[c].width = 14

    # Settings: everything needed to understand (and repeat) the run
    st = wb.create_sheet("Settings")
    t, d, f_ = prof["thresholds"], prof["duplicates"], prof["filters"]
    rows = [
        ("Run date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Run type", "Files moved" if moved else "Preview only (nothing moved)"),
        ("Profile", prof["name"]),
        ("Scanned folders", "; ".join(str(r) for r in roots)),
        ("Master folder", str(master)),
        ("Model", f"{prof['model']['name']} ({prof['model']['pretrained']})"),
        ("Min score to enter a folder", t["min_score"]),
        ("Flag for review below", t["review_below"]),
        ("Flag if 2nd folder is within", t["min_margin"]),
        ("Flag unsorted images with a score above", t["unsorted_floor"]),
        ("Skip images smaller than (px)", f"{f_['min_width']} x {f_['min_height']} (0 = off)"),
        ("Duplicate check", f"on, threshold {d['threshold']}, hash {d['hash_size']}, copies {d['copies']}"
         if d["enabled"] else "off"),
        ("How scores work", "CLIP probability summed over a folder's descriptions; below the minimum "
                            "score the image goes to the unsorted folder. Keyword rules override the AI."),
    ]
    st.append(["Setting", "Value"])
    for r_ in rows:
        st.append(list(r_))
    st.append([])
    st.append(["Folder", "Description", "Keywords"])
    start = st.max_row
    for c in prof["categories"]:
        for dsc in (c["descriptions"] or [c["name"]]):
            st.append([c["name"], dsc, ", ".join(c["keywords"])])
    for dsc in prof["other_descriptions"]:
        st.append([f"(something else -> {prof['unsorted_name']})", dsc, ""])
    for row in st.iter_rows():
        for c in row:
            c.font = font
    for c in list(st[1]) + list(st[start]):
        c.font, c.fill = head_font, head_fill
    for i in range(2, 2 + len(rows)):
        if isinstance(st.cell(row=i, column=2).value, float):
            st.cell(row=i, column=2).number_format = "0%"
    st.column_dimensions["A"].width = 44
    st.column_dimensions["B"].width = 80
    st.column_dimensions["C"].width = 30

    if skipped:
        sk = wb.create_sheet("Skipped")
        sk.append(["File", "Problem"])
        for c in sk[1]:
            c.font, c.fill = head_font, head_fill
        for p, e in skipped:
            sk.append([str(p), e])
        for row in sk.iter_rows(min_row=2):
            for c in row:
                c.font = font
        sk.column_dimensions["A"].width = 80
        sk.column_dimensions["B"].width = 60
    wb.save(path)


# =========================================================================== the whole run
def run_organize(a, prof, roots, master: Path, ask_move=False):
    names = [c["name"] for c in prof["categories"]]
    folders = names + [prof["unsorted_name"]]
    dd = prof["duplicates"]
    print(f"\nProfile: {prof['name']}  ({len(names)} folders + {prof['unsorted_name']})")
    print(f"Scanning {len(roots)} folder(s)...")
    files = scan(roots, master, prof["include_subfolders"])
    if not files:
        sys.exit("No images found.")
    print(f"Found {len(files)} image(s). Loading the model (the first run downloads it)...")
    clf = Classifier(prof)
    print(f"Model ready on {clf.device}.")
    recs, skipped = classify_all(clf, files, prof, a.batch_size)
    if not recs:
        sys.exit("No readable images.")
    if dd["enabled"]:
        mark_duplicates(recs, dd)
    master.mkdir(parents=True, exist_ok=True)
    plan_destinations(recs, master, prof)

    print(f"\nResult ({len(recs)} images):")
    print(f"  {'Folder':<18}{'Images':>7}{'Copies':>8}{'Review':>8}")
    for f in folders:
        rs = [r for r in recs if r["folder"] == f]
        print(f"  {f:<18}{len(rs):>7}{sum(r['dup'] == 'Copy' for r in rs):>8}{sum(r['review'] for r in rs):>8}")
    if skipped:
        print(f"  Skipped (unreadable): {len(skipped)}")

    preview = master / PREVIEW_NAME
    write_xlsx(preview, recs, skipped, prof, roots, master, moved=False)
    print(f"\nPreview sheet: {preview}")
    do_move = a.apply
    if not do_move and ask_move and not a.yes:
        print("Open the sheet to check the rows marked 'Needs review' before you answer.")
        do_move = ask_yes_no(f"Move these {len(recs)} images now (duplicates are set aside, nothing is deleted)?", True)
    if not do_move:
        print("Nothing was moved (preview only). Add --apply to move the files.")
        return
    moved, failed = apply_moves(recs, master, folders)
    final = master / XLSX_NAME
    if final.exists():
        final = master / f"organizer_data_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    write_xlsx(final, recs, skipped, prof, roots, master, moved=True)
    save_profile(prof, master / PROFILE_COPY)
    try:
        preview.unlink()
    except OSError:
        pass
    print(f"Moved {moved} file(s)" + (f", {failed} failed" if failed else "") + f".\nSheet: {final}")
    print(f"Undo everything with:  python image_organizer.py --undo --master \"{master}\"")


# =========================================================================== questions
def clean(s):
    return s.strip().strip('"').strip("'").strip()


def ask(prompt, default=""):
    v = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default


def ask_yes_no(prompt, default):
    while True:
        v = input(f"{prompt} [Y/N, Enter = {'Yes' if default else 'No'}]: ").strip().lower()
        if not v:
            return default
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        print("  Please type y or n.")


def ask_number(prompt, default, lo, hi, cast=float):
    while True:
        v = ask(prompt, str(default))
        try:
            x = cast(v)
            if lo <= x <= hi:
                return x
        except ValueError:
            pass
        print(f"  Please type a number from {lo} to {hi}.")


def ask_lines(prompt):
    """Several lines, one per entry. Empty line = done."""
    print(prompt + " (one per line, empty line when done)")
    out = []
    while True:
        v = input("  > ").strip()
        if not v:
            return out
        out.append(v)


def ask_folder_one(prompt, must_exist=True):
    while True:
        v = clean(input(prompt + ": "))
        if not v:
            continue
        p = Path(os.path.expandvars(os.path.expanduser(v))).resolve()
        if must_exist and not p.is_dir():
            print(f"  Not a folder: {p}")
            continue
        return p


def parse_folders(v):
    found = []
    for part in (re.findall(r'"([^"]+)"', v) or [clean(v)]):
        p = Path(os.path.expandvars(os.path.expanduser(part))).resolve()
        if p.is_dir():
            found.append(p)
        else:
            print(f"  Not a folder, ignored: {p}")
    return found


def ask_folders(label):
    roots, cwd = [], Path.cwd()
    while True:
        prompt = f"{label} (Enter = {cwd})" if not roots else f"Another folder ({len(roots)} added, Enter = done)"
        v = input(prompt + ": ").strip()
        if not v:
            if roots:
                return roots
            roots = [cwd]
            continue
        roots += parse_folders(v)


# =========================================================================== profile editor
def valid_folder_name(p, name, skip=None):
    probs = validate({**p, "categories": [{"name": name}] + [c for c in p["categories"] if c is not skip]})
    return [x for x in probs if name in x or "reserved" in x]


def ask_new_name(p, skip=None):
    while True:
        n = ask("  Folder name").strip()
        if not n:
            print("  A name is required.")
            continue
        probs = valid_folder_name(p, n, skip)
        if not probs:
            return n
        print("  " + "; ".join(probs))


def show_profile(p):
    print(f"\n=== Profile: {p['name']} ===")
    for i, c in enumerate(p["categories"], 1):
        kw = f", keywords: {', '.join(c['keywords'])}" if c["keywords"] else ""
        print(f"  {i}) {c['name']}  ({len(c['descriptions'])} descriptions{kw})")
    if not p["categories"]:
        print("  (no folders yet)")
    t = p["thresholds"]
    print(f"  Unsorted folder: {p['unsorted_name']}   |   needs score >= {t['min_score']:.0%} to enter a folder")
    d = p["duplicates"]
    print("  Duplicates: " + (f"on (strictness {d['threshold']}, copies {d['copies']})" if d["enabled"] else "off"))
    f = p["filters"]
    if f["min_width"] or f["min_height"]:
        print(f"  Tiny-image filter: under {f['min_width']}x{f['min_height']} px go to unsorted")


def edit_category(p, c):
    while True:
        print(f"\n--- Folder '{c['name']}' ---")
        for i, d in enumerate(c["descriptions"], 1):
            print(f"  {i}. {d}")
        if not c["descriptions"]:
            print("  (no descriptions: the folder name itself is used)")
        print(f"  Keywords (file or subfolder names that force this folder): {', '.join(c['keywords']) or '-'}")
        print("  1 = Add descriptions   2 = Remove a description   3 = Set keywords\n"
              "  4 = Rename             B = Back")
        ch = ask("Choose", "B").lower()
        if ch == "1":
            c["descriptions"] += ask_lines("What does this folder's content look like? Short phrases, "
                                           "e.g. 'a Bajaj logo', 'a scanned invoice'")
        elif ch == "2" and c["descriptions"]:
            n = ask_number("  Remove which number", 1, 1, len(c["descriptions"]), int)
            c["descriptions"].pop(n - 1)
        elif ch == "3":
            raw = ask("  Keywords, separated by commas (empty = none)", "")
            c["keywords"] = [k.strip() for k in raw.split(",") if k.strip()]
        elif ch == "4":
            c["name"] = ask_new_name(p, skip=c)
        elif ch == "b":
            return


def edit_strictness(p):
    t = p["thresholds"]
    print("\nHow sure must the sorter be before it puts an image in a folder?\n"
          "  1 = Strict    (fewer mistakes, more images left in Unsorted)\n"
          "  2 = Balanced  (default)\n"
          "  3 = Loose     (sorts more, a few more mistakes)\n"
          "  4 = Custom numbers")
    ch = ask("Choose", "2")
    presets = {"1": (0.70, 0.85, 0.35), "2": (0.50, 0.75, 0.25), "3": (0.35, 0.60, 0.15)}
    if ch in presets:
        t["min_score"], t["review_below"], t["min_margin"] = presets[ch]
    elif ch == "4":
        t["min_score"] = ask_number("  Minimum score to enter a folder (0-1)", t["min_score"], 0, 1)
        t["review_below"] = ask_number("  Flag for review below (0-1)", t["review_below"], 0, 1)
        t["min_margin"] = ask_number("  Flag if the runner-up is closer than (0-1)", t["min_margin"], 0, 1)


def edit_duplicates(p):
    d = p["duplicates"]
    d["enabled"] = ask_yes_no("Remove duplicates inside each folder?", d["enabled"])
    if not d["enabled"]:
        return
    d["threshold"] = ask_number("  Strictness 0-8 (0 = identical only, 6 = also resized/recompressed)",
                                d["threshold"], 0, 16, int)
    print("  Where should the copies go?\n"
          "    1 = a 'copies' subfolder inside each folder (default)\n"
          "    2 = one separate '_duplicates' folder in the master folder")
    d["copies"] = "separate" if ask("  Choose", "1" if d["copies"] == "inside" else "2") == "2" else "inside"


def edit_profile(p, path: Path):
    p = with_defaults(p)
    while True:
        show_profile(p)
        print("\n  1 = Add a folder          2 = Edit a folder        3 = Remove a folder\n"
              "  4 = How sure it must be   5 = Skip tiny images     6 = Duplicates\n"
              "  S = Save and exit         Q = Exit without saving")
        ch = ask("Choose", "S").lower()
        if ch == "1":
            c = {"name": ask_new_name(p), "keywords": [], "descriptions": []}
            c["descriptions"] = ask_lines("Describe what belongs in it, short phrases like 'a scanned invoice' "
                                          "(empty = use the folder name)")
            raw = ask("  Keywords that force this folder, separated by commas (empty = none)", "")
            c["keywords"] = [k.strip() for k in raw.split(",") if k.strip()]
            p["categories"].append(c)
        elif ch == "2" and p["categories"]:
            n = ask_number("  Edit which folder number", 1, 1, len(p["categories"]), int)
            edit_category(p, p["categories"][n - 1])
        elif ch == "3" and p["categories"]:
            n = ask_number("  Remove which folder number", 1, 1, len(p["categories"]), int)
            if ask_yes_no(f"  Remove '{p['categories'][n - 1]['name']}'?", False):
                p["categories"].pop(n - 1)
        elif ch == "4":
            edit_strictness(p)
        elif ch == "5":
            p["filters"]["min_width"] = ask_number("  Minimum width in px (0 = off)", p["filters"]["min_width"], 0, 100000, int)
            p["filters"]["min_height"] = ask_number("  Minimum height in px (0 = off)", p["filters"]["min_height"], 0, 100000, int)
        elif ch == "6":
            edit_duplicates(p)
        elif ch == "s":
            problems = validate(p)
            if problems:
                print("\nCannot save yet:\n  - " + "\n  - ".join(problems))
                continue
            save_profile(p, path)
            print(f"Saved: {path}")
            return p
        elif ch == "q":
            return None


def new_profile_flow():
    name = ask("Name for the new profile", "My profile")
    path = PROFILES_DIR / f"{slug(name)}.json"
    if path.exists() and not ask_yes_no(f"{path.name} exists. Overwrite it?", False):
        return None
    existing = list_profiles()
    print("Start from:\n  0 = an empty profile")
    for i, e in enumerate(existing, 1):
        print(f"  {i} = a copy of '{e.stem}'")
    ch = ask_number("Choose", 0, 0, len(existing), int)
    p = with_defaults(load_profile(existing[ch - 1])) if ch else with_defaults({"categories": []})
    p["name"] = name
    return edit_profile(p, path) and path


def choose_profile():
    profiles = list_profiles()
    if len(profiles) == 1:
        return profiles[0]
    print("\nProfiles:")
    for i, pth in enumerate(profiles, 1):
        try:
            nm = json.load(open(pth, encoding="utf-8")).get("name", pth.stem)
        except (OSError, json.JSONDecodeError):
            nm = pth.stem
        print(f"  {i}) {nm}  ({pth.name})")
    return profiles[ask_number("Which profile", 1, 1, len(profiles), int) - 1]


def wizard(a):
    ensure_default_profile()
    while True:
        print(f"\n=== Image organizer v{VERSION} ===\n")
        print("  1) Organize images  (sort into folders, then remove duplicates)\n"
              "  2) Edit a sorting profile (what the folders are and how strict it is)\n"
              "  3) Create a new sorting profile\n"
              "  4) Undo a previous run\n"
              "  Q) Quit")
        ch = ask("Choose", "1").lower()
        if ch == "2":
            pth = choose_profile()
            edit_profile(load_profile(pth), pth)
        elif ch == "3":
            new_profile_flow()
        elif ch == "4":
            a.undo = True
            a.master = ask_folder_one("Master folder of the run to undo")
            return True
        elif ch == "q":
            return False
        else:
            a.profile_path = choose_profile()
            roots = ask_folders("Folder with the images")
            a.roots, notes = normalize_roots(roots, True)
            for n in notes:
                print(f"  Note: {n}")
            default = default_master(a.roots)
            print(f"\nMaster folder (created automatically): {default}")
            if ask_yes_no("Pick a different master folder?", False):
                a.master = ask_folder_one("Master folder location", must_exist=False)
            a.ask_move = True
            return True


# =========================================================================== main
def main():
    ap = argparse.ArgumentParser(description="Sort images into folders by content, then remove duplicates.")
    ap.add_argument("roots", nargs="*", help="folder(s) with the images; leave out for the guided menu")
    ap.add_argument("--profile", help="profile name or path (default: the first one in the profiles folder)")
    ap.add_argument("--master", help="master folder (default: <folder>_organized next to the scanned folder)")
    ap.add_argument("--apply", action="store_true", help="really move the files (default: preview only)")
    ap.add_argument("--undo", action="store_true", help="move everything back using moves_log.csv")
    ap.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--no-subfolders", dest="recursive", action="store_false", help="top level only")
    ap.add_argument("--no-dedupe", action="store_true", help="skip the duplicate step for this run")
    ap.add_argument("--min-score", type=float, help="override the profile's minimum score (0-1)")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--list-profiles", action="store_true")
    ap.add_argument("--edit-profile", nargs="?", const="", metavar="NAME", help="open the profile editor")
    a = ap.parse_args()
    a.ask_move, a.profile_path = False, None

    if a.list_profiles:
        for pth in list_profiles():
            print(pth)
        return
    if a.edit_profile is not None:
        pth = resolve_profile(a.edit_profile or None)
        edit_profile(load_profile(pth), pth)
        return

    if not a.roots and not a.undo:
        if not wizard(a):
            return
    if a.undo:
        if not a.master:
            sys.exit("--undo needs --master (the master folder of the run)")
        undo(Path(a.master).resolve())
        return

    if not isinstance(a.roots[0], Path):  # command line
        paths = []
        for r in a.roots:
            p = Path(r).resolve()
            if not p.is_dir():
                sys.exit(f"Not a folder: {p}")
            paths.append(p)
        a.roots = paths
        a.ask_move = sys.stdin.isatty()
    prof = load_profile(a.profile_path or resolve_profile(a.profile))
    if not a.recursive:
        prof["include_subfolders"] = False
    if a.no_dedupe:
        prof["duplicates"]["enabled"] = False
    if a.min_score is not None:
        prof["thresholds"]["min_score"] = a.min_score
    roots, notes = normalize_roots(a.roots, prof["include_subfolders"])
    for n in notes:
        print(f"Note: {n}")
    master = Path(a.master).resolve() if a.master else default_master(roots)
    run_organize(a, prof, roots, master, ask_move=a.ask_move)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        sys.exit(1)
