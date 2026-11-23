# Image organizer and Duplicate image finder

Two local command-line tools in one repo. The **Image organizer** sorts images into folders by what they show (for example Bajaj, Royal Enfield, Tata and Unsorted), then removes duplicates inside each folder and records everything in one Excel sheet. The **Duplicate image finder** finds duplicate and near-duplicate images across one or many folders with perceptual hashing (pHash) and moves the copies aside. Both run from any folder with guided questions, are dry run by default, fully logged and reversible, and never delete anything.

## What it is

Two Python scripts: no framework, no database, no GUI and no server.

- `image_organizer.py` (v3.0) is the complete workflow: sort by content with a local image-understanding model (CLIP), dedupe inside each folder, and write one Excel sheet, one log and one undo. What gets sorted is defined by a profile you can edit from a menu.
- `duplicate_image_finder.py` (v2.7) is the standalone duplicate step. The organizer uses the same method and defaults for its duplicate step, so results match.

## Which one to use

| You want to | Use |
|---|---|
| Sort a pile of images into brand or category folders, then clean out duplicates, with a sheet of all the data | Image organizer |
| Only find and set aside duplicates, including a photo that exists in two different folders | Duplicate image finder |
| Change what is sorted, how strict it is, or add folders | Image organizer, profile editor (menu option 2 or 3) |

The organizer finds duplicates inside each folder only. The Duplicate image finder compares all scanned folders together.

## Public links

None. These are local tools and have no website or hosting.

## Folder layout

- Root: `image_organizer.py`, `run_image_organizer.bat`, `profiles/` (sorting profiles, for example `dealership_brands.json`), `duplicate_image_finder.py`, `run_duplicate_image_finder.bat`, `README.md`, `CHANGELOG.md`. Keep each `.py` and its `.bat` together; the files can be kept anywhere. The organizer looks for `profiles/` next to its script.
- Created by the **Image organizer** in its master folder (default `<scanned folder name>_organized`, next to the scanned folder): one folder per profile folder, `organizer_data.xlsx`, `moves_log.csv`, `profile_used.json`.
- Created by the **Duplicate image finder** in its output folder (default `<scanned folder name>_dedupe_output`, next to the scanned folder; with several folders `multi_<N>_folders_dedupe_output` in their common parent): `status_report.txt`, `moves_log.csv` and `copies/` (default mode).
- Install, Python 3.9+. One virtual environment serves both tools, and both launchers use `finder-env` next to them if it exists:

```
python -m venv finder-env
finder-env\Scripts\activate
pip install open_clip_torch torch pillow numpy openpyxl imagehash
```

The Duplicate image finder alone needs only `pip install imagehash pillow numpy`. The launchers offer to install what is missing.

## Main files

| File | Purpose |
|---|---|
| `image_organizer.py` | Sort by content, dedupe per folder, Excel sheet, log, undo and the profile editor |
| `run_image_organizer.bat` | Windows launcher: finds Python, checks the packages (offers to install them), then runs the organizer |
| `profiles/*.json` | Sorting profiles: folders, descriptions, keywords, thresholds, duplicate settings |
| `duplicate_image_finder.py` | Standalone tool: scan, hash, group, move, log and undo |
| `run_duplicate_image_finder.bat` | Windows launcher for the Duplicate image finder |
| `README.md` | This file |
| `CHANGELOG.md` | Version history of both tools |
| `organizer_data.xlsx`, `moves_log.csv`, `profile_used.json` | Created by the organizer in its master folder |
| `status_report.txt`, `moves_log.csv` | Created by the Duplicate image finder in its output folder |

## Image organizer

The organizer sorts images with a local image-understanding model (CLIP, no internet after the first download), removes duplicates inside each folder, and records everything in one Excel sheet. One launcher, one log, one undo. Nothing is ever deleted.

### What it does

1. **Sort.** CLIP compares every image with the descriptions you gave each folder. Optional keyword rules and a tiny-image filter run as well. Images that do not clearly belong anywhere go to the unsorted folder.
2. **Dedupe.** Inside each folder, near-identical images are found. The best one stays (highest resolution, then largest file, then oldest, then shortest path). The copies are set aside in a `copies` subfolder of that folder, or in one `_duplicates` folder.
3. **Record.** `organizer_data.xlsx` has one row per image and a live summary. `moves_log.csv` records every move for undo.

What gets sorted is defined by a **profile**, so the same tool works for dealership brands, invoices, product photos or anything else.

### Install and run

```
pip install open_clip_torch torch pillow numpy openpyxl imagehash
```

Python 3.9+. The first run downloads the model once (roughly 600 MB). On Windows, double-click `run_image_organizer.bat`: it finds Python, offers to install missing packages and opens the menu. Keep `image_organizer.py`, the `.bat` and the `profiles` folder together.

Menu: **1** organize, **2** edit a profile, **3** create a profile, **4** undo.

Command line:

| Command | Effect |
|---|---|
| `python image_organizer.py "D:\photos"` | Preview only: nothing moves, a preview sheet is written |
| `... --apply --yes` | Sort, dedupe and move |
| `... --profile invoices` | Use another profile (name or path) |
| `... --master "E:\out"` | Choose the master folder |
| `... --no-dedupe` / `--no-subfolders` | Skip the duplicate step / top level only |
| `... --min-score 0.6` | Override the profile's minimum score for this run |
| `--edit-profile [name]`, `--list-profiles` | Profile editor, list profiles |
| `--undo --master "E:\photos_organized"` | Put every file back |

### Result layout

```
<name>_organized/              (next to the scanned folder, or your --master)
  Bajaj/  Royal Enfield/  Tata/  Unsorted/       one folder per profile folder
    <each>/copies/                               duplicates of that folder (default)
  organizer_data.xlsx    every image, scores, duplicates, summary, settings
  moves_log.csv          used by undo
  profile_used.json      the profile this run used
```

A preview run writes `organizer_preview.xlsx` only. After undo the log is renamed `moves_log_undone_<time>.csv`, so the master folder can be reused.

### Profiles

A profile is a JSON file in `profiles/`. Edit it from the menu or by hand. Missing settings fall back to defaults.

```json
{
  "name": "Invoices",
  "categories": [
    {"name": "Invoices", "descriptions": ["a scanned invoice", "a bill"], "keywords": ["invoice", "inv_"]},
    {"name": "Receipts", "descriptions": ["a shop receipt"], "keywords": []}
  ],
  "other_descriptions": ["a photo of a person", "a screenshot"],
  "unsorted_name": "Unsorted",
  "thresholds": {"min_score": 0.5, "review_below": 0.75, "min_margin": 0.25, "unsorted_floor": 0.2},
  "filters": {"min_width": 0, "min_height": 0},
  "duplicates": {"enabled": true, "threshold": 6, "hash_size": 8, "copies": "inside", "copies_folder": "copies"},
  "include_subfolders": true
}
```

| Setting | Meaning |
|---|---|
| `categories[].name` | Folder name. Must be a valid Windows folder name and unique. |
| `categories[].descriptions` | Short phrases for what belongs in the folder, such as `a Bajaj logo`. 3 to 6 work well. If empty, the folder name is used. |
| `categories[].keywords` | If the file name or a subfolder name under the scanned folder contains one, that folder is chosen. If keywords of two folders match, the AI decides and the image is flagged. If the AI strongly disagrees, the image is flagged for review. |
| `other_descriptions` | Things that are none of your folders. They give unrelated images somewhere to go, so they land in unsorted instead of being forced into a folder. Add the look-alikes you want rejected (for example other brands). |
| `thresholds.min_score` | Score an image needs to enter a folder. Raise for fewer mistakes, lower to sort more. |
| `thresholds.review_below` / `min_margin` | Flag for review when the score is low, or the runner-up folder is close. |
| `thresholds.unsorted_floor` | Flag unsorted images that still show some signal for a folder. |
| `filters.min_width` / `min_height` | Images smaller than this go to unsorted (0 = off). |
| `duplicates.threshold` | 0 = identical only, 6 = also resized or recompressed copies, higher = looser. |
| `duplicates.copies` | `inside` = a `copies` subfolder in each folder, `separate` = one `_duplicates` folder. |
| `prompt_template`, `category_weight`, `other_weight`, `model` | Advanced. Each folder counts `category_weight` in total however many descriptions it has, so folders with fewer descriptions are not disadvantaged. |

### How the score works

Each description gets a probability from the model. A folder's score is the sum over its descriptions, and the "something else" group competes with them. An image enters the folder with the highest score if that score reaches `min_score`; otherwise it goes to unsorted. The Excel sheet shows every score, what matched best, who decided (AI, keyword or size filter), and why an image needs review.

### Tuning

- Too many images in unsorted: choose **Loose** in the editor, or add more descriptions for the folder.
- Wrong images in a folder: add the look-alikes to `other_descriptions`, or choose **Strict**.
- Sort the sheet by "Top score" and check rows marked "Needs review" first.
- For more accuracy at the cost of speed, set `model` to `ViT-L-14` with `laion2b_s32b_b82k`.

### Not yet included

- Example images per folder ("these 20 photos are Bajaj") as an alternative to text descriptions.
- A window-based interface for people who do not use a terminal.
- Dedupe across different folders (duplicates are found inside each folder).

## Duplicate image finder

### What it is

A single Python script: no framework, no database, no GUI and no server. It scans a folder recursively, hashes every supported image, groups images that look the same, keeps one original per group and moves the rest into a `copies` folder. Nothing is ever deleted.

Run it with no arguments and it asks what to do. The script can sit in any folder, it does not need to be inside the photos.

Several folders can be scanned in one run. They are hashed together, so a photo that exists in two different folders is detected as well. Nested subfolders are included by default.

It was built to clean up large nested photo folders where the same picture exists several times (re-saved, resized, recompressed or lightly edited) and the copies need to be set aside per folder rather than deleted.

### Command options

| Option | Default | Description |
|---|---|---|
| `root` (one or more) | asked if omitted | Folder(s) to scan, all compared together. Leave out to get the guided questions |
| `--yes`, `-y` | off | Skip the confirmation questions (for scripts). Without it, confirmations are asked in the guided mode and whenever the script is run from a terminal |
| `--no-subfolders` | off | Scan only the top level of each folder. By default nested subfolders are included |
| `--output PATH` | `<name>_dedupe_output` in the parent folder | Output folder for the status report, log and copies. Created if missing |
| `--apply` | off | Actually move files. Without it the script only prints what it would do |
| `--undo` | off | Restore every file listed in `moves_log.csv` |
| `--mode output\|own\|original` | `output` | Where the copies are moved to |
| `--threshold N` | `6` | Max Hamming distance to count as a duplicate |
| `--hash-size N` | `8` | `8` = 64-bit hash, `16` = 256-bit hash |

### How duplicates are handled

- **Supported formats:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tif`, `.tiff`. Corrupt or unreadable files are reported and skipped.
- **Original selection:** in each group the original is the image with the highest resolution, then the largest file size, then the oldest modified date, then the shortest path.
- **Grouping:** greedy. Each remaining image is compared against the original only, never against other copies, so chains of slowly changing images do not merge into one group.
- **Several folders:** all images from all folders form one pool. The original is chosen by the same rule across folders, so a copy can sit in a different folder from its original.
- **Overlapping folders:** repeated folders are ignored and a folder already inside another selected folder is skipped (with a note), so no image is processed twice.
- **Mode `output` (default):** each copy goes into `<output>\copies\`, keeping its subfolder path relative to the scanned folder. With several folders there is one subfolder per scanned folder (`copies\<folder name>\...`; same names become `name_2`).
- **Mode `own`:** each copy goes into a `copies` folder inside the folder it already sits in.
- **Mode `original`:** each copy goes into a `copies` folder next to the image it duplicates.
- **Name clashes:** if the name already exists in `copies`, the file becomes `name_1.jpg`, `name_2.jpg` and so on.
- **Re-runs:** existing `copies` folders and the output folder (when it sits inside the scanned folder) are skipped, so running again is safe.
- Nothing is deleted. Files are only moved.

Example: `photos\trip\a.jpg` is the original and `photos\backup\a_copy.jpg` is the duplicate.

| Mode | Result |
|---|---|
| `output` | `photos_dedupe_output\copies\backup\a_copy.jpg` |
| `own` | `photos\backup\copies\a_copy.jpg` |
| `original` | `photos\trip\copies\a_copy.jpg` |

### Usage

**Windows launcher:** double-click `run_duplicate_image_finder.bat` for the guided mode, or drag one or more folders onto it to scan them. Arguments typed after it are passed on, for example `run_duplicate_image_finder.bat "D:\photos" --apply`. It uses `finder-env\Scripts\python.exe` next to it if that virtual environment exists, otherwise `py -3`, otherwise `python`. If `imagehash`, `pillow` or `numpy` are missing it offers to install them. The folder you start it from is not changed, so "Enter = current folder" works as expected.

**Guided (any folder):** run `python duplicate_image_finder.py` with no path (or double-click the launcher). It first asks how to run:

1. **Default** (just press Enter). One question only: the folder(s) to scan (Enter = the folder you are standing in; several folders can be pasted or dragged in at once). Everything else is automatic: nested subfolders are included, threshold 6, copies go into one output folder created next to the scanned folder (`<name>_dedupe_output`), and the files are really moved, nothing is deleted. It shows the folders and file counts, then asks one question, "Move these N copies now?" (Enter = Yes). The skipped steps are the options below, the preview and the question before hashing. On Windows the output folder opens when it finishes.
2. **Customised.** Asks everything, in order:
   1. Folder(s) to scan. Enter = the folder you are standing in. After each folder it asks for another one; press Enter on an empty line when done. Several quoted paths on one line also work (drag and drop of multiple folders).
   2. Include nested subfolders (default yes).
   3. Select an output folder yourself? Answer `y` and type its location (created if missing), or `n` to have one created automatically in the parent folder of the scanned folder.
   4. Where the copies go (output folder, own folder or next to the original).
   5. Threshold (Enter = 6).
   6. Preview only (default) or move files.

   Then two confirmations with real numbers (see Confirmation below).
3. **Undo a previous run.** Asks for the folder(s) that were scanned and restores from the log.

**Command line:**

1. Preview first (moves nothing): `python duplicate_image_finder.py "D:\photos"` or several folders: `python duplicate_image_finder.py "D:\photos" "E:\phone" "F:\old"`
2. Read the printed list. Each line shows the copy, its original, the distance and where it would go.
3. Move the copies: `python duplicate_image_finder.py "D:\photos" --apply` (add `--output "E:\out"` or `--mode original` if wanted).
4. To reverse everything: `python duplicate_image_finder.py "D:\photos" --undo` (add the same `--output` if you used one).
5. Check the `copies` folders, then delete them by hand only when you are sure.

### Finding the output folder

The output folder is created as soon as it is chosen, and its full path is printed, so it can be opened in Explorer while the other questions are still being answered. The default one sits **next to** the scanned folder, not inside it: for `D:\Downloads` it is `D:\Downloads_dedupe_output`, so look in `D:\`. At the end of a guided run on Windows the tool offers to open it. Undo never creates a folder; it only looks for the log in the one it prints.

### Confirmation

In **Customised** mode both questions below are asked. In **Default** mode only the second one is asked, and its default answer is Yes.

Before anything is processed the tool shows which folders are affected and how many files, and waits for a yes:

1. **After scanning, before hashing:** each folder with its image count and the total. Question: hash and compare these images now? (default yes). Nothing has been changed at this point.
2. **After duplicates are found, before moving (`--apply` only):** each folder with its image count and the number of copies that will be moved out of it, the total, and the destination. Question: move these copies now? (default **no**).

Answering no stops the run, moves nothing and marks the status report `CANCELLED`. A dry run shows the same per-folder table but never asks to move. The time spent waiting for your answer is not counted in the elapsed time. In the CLI the questions appear when run from a terminal; use `--yes` to skip them.

### Status report

`status_report.txt` is created in the output folder as soon as the run starts and is rewritten every second (open it in Notepad and reopen to refresh). It shows:

- Status (`RUNNING`, `WAITING FOR YOUR CONFIRMATION`, `COMPLETED`, `CANCELLED`, `INTERRUPTED` or `FAILED`), start time, last update and elapsed time.
- An overall progress bar with percentage.
- For the current step: items done, **items remaining**, speed and **time remaining** with the expected finish clock time.
- A checklist of the four steps (scanning, hashing, finding duplicates, moving) with the time each took.
- A `FOLDERS AFFECTED` list: images per folder and, once duplicates are found, copies per folder.
- Unreadable files that were skipped, and a final result summary.

Time remaining is calculated from the speed of the current step so far, so it settles after the first few seconds. Hashing is the longest step. The same progress is also shown as one live line in the console.

### Maintenance notes

- Threshold guide for the 64-bit hash: 0 to 2 for exact or re-saved copies only, 3 to 6 for resized, recompressed or lightly edited images (default 6), 7 to 10 aggressive with false positives expected. With `--hash-size 16`, multiply by about 4.
- Always dry-run first. A loose threshold can flag burst shots or similar-looking photos that are genuinely different.
- Supported extensions are the `EXTS` set at the top of `duplicate_image_finder.py`. Add an extension there to include it.
- The log file name is the `LOG_NAME` constant, the report name is `STATUS_NAME`, the folder name is `COPIES` and the default output folder suffix is `OUT_SUFFIX`, all at the top of the script.
- Logs named `phash_moves_log.csv` (written before v2.7) are still found and restored by `--undo`.
- `--undo` skips any file whose moved copy is missing or whose original location is now taken, and prints a line for each skip. It also removes `copies` folders that become empty. Logs made by v1.x in the scanned folder are still found.
- The log is appended on every `--apply` run and each move is written immediately, so one `--undo` restores all runs in reverse order, even after an interrupted run.
- The default output folder depends on the folder(s) scanned. When undoing, give the same folders (or the same `--output`).
- Not detected: rotated, mirrored or heavily cropped duplicates. GIFs and multi-page TIFFs are hashed by their first frame only. Videos and audio are not supported.
- Comparison is O(n²) but vectorised with numpy. Tens of thousands of images are fine; hashing is the slow part. For hundreds of thousands, use a hash cache or a BK-tree.

## Before running on a real library

**Image organizer**

- [ ] The profile lists exactly the folders you want, and each folder has a few clear descriptions
- [ ] Preview run done and `organizer_preview.xlsx` opened; rows marked "Needs review" checked
- [ ] Strictness chosen on purpose (Strict, Balanced or Loose), and look-alikes added to the "something else" descriptions where needed
- [ ] Master folder is where you want it (default is next to the scanned folder)
- [ ] After moving, `moves_log.csv` and `organizer_data.xlsx` exist in the master folder, and a few images in each folder look right

**Duplicate image finder**

- [ ] Dry run completed and the printed pairs checked by eye
- [ ] Folder list and file counts in the confirmation screens match what you expected
- [ ] Threshold chosen deliberately (default 6 is not always right)
- [ ] Mode chosen: `output`, `own` or `original`
- [ ] All folders to scan are added, and nested subfolders are included or excluded on purpose
- [ ] Output folder is where you want it (default is next to the scanned folder)
- [ ] The scanned folder is writable (files are moved, not copied, so no extra disk space is needed, except when the output folder is on another drive)
- [ ] After `--apply`, `moves_log.csv` exists in the output folder and `status_report.txt` says `COMPLETED`
- [ ] A spot check of a few `copies` folders looks right

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.9+ |
| Sorting by content | `open_clip_torch` (CLIP, default ViT-B-32) on `torch`, runs locally on CPU or GPU |
| Hashing | `imagehash` (`phash`) on `Pillow` images |
| Comparison | `numpy` vectorised Hamming distance |
| Spreadsheet | `openpyxl` (Data, Summary, Settings and Skipped sheets, live formulas) |
| Profiles | JSON files in `profiles/`, edited from a built-in menu |
| Logging | CSV move logs and, for the Duplicate image finder, a live `status_report.txt`; standard library only |
| Launchers | Windows batch files (`run_image_organizer.bat`, `run_duplicate_image_finder.bat`) |
| Hosting | None, runs locally (commands shown for Windows PowerShell) |
