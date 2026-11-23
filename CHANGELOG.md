# Changelog - Duplicate image finder and Image organizer

All notable changes to the Duplicate image finder (formerly phash_dedupe) and the Image organizer, tracked in one numbered sequence. v3.0 introduced the Image organizer (`image_organizer.py`); entries before it belong to `duplicate_image_finder.py`. Older entries use the file names that were current at the time.

## v3.1 - Folder-trained image classifier
**Date:** 23-11-2026

- Added `train_from_folders.py`, an example-based classifier that learns visual image prototypes from labeled folders. The immediate child folder under the training root becomes the category; deeper folders such as `Collection Bin` are treated as organization only.
- Added `run_folder_trainer.bat` for Windows. `train` builds a reusable model folder with normalized CLIP embeddings, labels, source paths, a training manifest and a validation report. `classify` creates a CSV preview by default and sends low-confidence or close predictions to `Review`.
- Classification is safe by default: no files are copied or moved unless `--apply` is supplied. With `--apply`, classified images are copied into category folders; source images remain unchanged.
- Trained the initial showroom model from `Showroom Media (For everyone)`: 254 images across `Bajaj 3 Wheelers` (88), `Royal Enfield` (100) and `Tata Trucks` (66), with no unreadable images. The preliminary held-out validation was 48/50 (96%).
- Documented the folder-trained workflow and commands in `README.md`.
- Updated `run_folder_trainer.bat` so double-clicking opens a menu for training the showroom dataset or classifying a new folder; command-line `train` and `classify` usage remains available.
- Fixed the inference-time PyTorch scalar conversion warning in `image_organizer.py`.
- Updated `run_image_organizer.bat` to anchor itself to its own folder, show startup status, avoid heavyweight ML imports during the dependency check and keep runtime errors visible when double-clicked.
- Files Changed: `train_from_folders.py`, `run_folder_trainer.bat`, `run_image_organizer.bat`, `README.md`, `CHANGELOG.md`.

## v3.0 - Image organizer: sort by content, then remove duplicates, in one tool
**Date:** 22-11-2026

- New tool `image_organizer.py` with launcher `run_image_organizer.bat` and a default profile `profiles/dealership_brands.json`. `README.md` is now one combined guide for both tools (what each is and when to use which, install, the organizer, the duplicate finder, a checklist for each, tech stack). `duplicate_image_finder.py` is unchanged (its own version stays 2.7) and still works on its own.
- **Sort:** a local image-understanding model (CLIP, via `open_clip_torch`) compares every image with short descriptions given for each folder. The default profile has Bajaj, Royal Enfield and Tata plus Unsorted. Logos, vehicles and signboards are only clues for the brand; the brand alone decides the folder. Images that do not clearly belong anywhere go to Unsorted. Transparent PNG logos are placed on white before scoring.
- **Scoring:** a folder's score is the model's probability summed over its descriptions, and an extra "something else" group (other brands, people, documents, and so on) competes with them. Starting thresholds: 0.50 to enter a folder, flagged for review below 0.75 or when the runner-up is within 0.25, and Unsorted images with a score above 0.20 are flagged.
- **Dedupe:** after sorting, duplicates are found inside each folder with the same method and defaults as v2.7 (pHash, hash size 8, threshold 6, same rule for the image that is kept, copies compared with the original only). Copies go to a `copies` subfolder of their folder, or to one `_duplicates` folder. Nothing is deleted.
- **One record:** `organizer_data.xlsx` has a Data sheet (paths, size, resolution, every folder score, best match, who decided, needs review and why, duplicate status, duplicate of, hash distance, status), a Summary sheet with live formulas (images, kept, copies, share, needs review per folder), a Settings sheet (profile, thresholds and every description used) and a Skipped sheet for unreadable files. One log `moves_log.csv` covers both steps, and one `--undo` restores everything. After an undo the log is renamed `moves_log_undone_<time>.csv`, so the master folder can be reused.
- **Profiles:** what is sorted is defined by a JSON profile in the `profiles` folder. A built-in menu creates and edits profiles with no file editing: add, edit and remove folders, descriptions per folder, keywords, strictness (Strict, Balanced, Loose or custom numbers), tiny-image filter and duplicate settings. New profiles start empty or as a copy of an existing one. Folder names are checked (valid on Windows, unique, not reserved).
- **Rules besides the model:** keywords per folder (a file or subfolder name containing one forces that folder; two folders matching hands the decision back to the model and flags the image; a strong disagreement from the model flags the image) and a minimum width and height (smaller images go to Unsorted).
- **Running it:** the guided menu offers 1) Organize, 2) Edit a profile, 3) Create a profile, 4) Undo. An organize run classifies first, writes a preview sheet, shows images, copies and review counts per folder and asks before moving (Enter = Yes). Command line: preview by default, `--apply` to move, plus `--profile`, `--master`, `--yes`, `--no-dedupe`, `--no-subfolders`, `--min-score`, `--edit-profile`, `--list-profiles` and `--undo`.
- Known limits: the first run downloads the model (roughly 600 MB); the thresholds are starting values to tune on real images; duplicates are found inside each folder only, not across folders; example images per folder are not supported yet; there is no window-based interface yet.
- Files Changed: `image_organizer.py` (new), `run_image_organizer.bat` (new), `profiles/dealership_brands.json` (new), `README.md`, `CHANGELOG.md`.

## v2.7 - Renamed to Duplicate image finder
**Date:** 21-11-2026

- Renamed `phash_dedupe.py` to `duplicate_image_finder.py` and `run_phash_dedupe.bat` to `run_duplicate_image_finder.bat`. The launcher looks for the new script name.
- README and changelog headings, usage examples and the script's own help text use the new names. The virtual environment folder the launcher looks for is now `finder-env` (was `phash-env`).
- Move log renamed from `phash_moves_log.csv` to `moves_log.csv`. `--undo` still finds and restores logs with the old name, including when old and new logs are in the same output folder.
- Internal hashing is still pHash; only the tool name and file names changed.
- Files Changed: `duplicate_image_finder.py`, `run_duplicate_image_finder.bat`, `README.md`, `CHANGELOG.md`.

## v2.6 - Default and Customised modes
**Date:** 21-11-2026

- The guided mode now starts with a choice: 1) Default, 2) Customised, 3) Undo a previous run. Pressing Enter picks Default.
- **Default** needs one answer, the folder(s) to scan (Enter = current folder, several folders can be pasted or dragged in at once). It uses fixed settings: nested subfolders included, threshold 6, copies moved into one output folder created next to the scanned folder, files really moved (nothing deleted, undo available). It skips the preview and the "hash now?" question, shows the folders and file counts, and asks a single "Move these N copies now?" with Enter = Yes. On Windows the output folder opens automatically at the end.
- **Customised** is the previous guided flow with every option (folders, subfolders, output folder, copies mode, threshold, preview or move) and both confirmations.
- Command-line use is unchanged.
- Files Changed: `phash_dedupe.py`, `README.md`, `CHANGELOG.md`.

## v2.5 - Output folder is created and shown immediately
**Date:** 21-11-2026

- The output folder is now created as soon as it is chosen, not after the last question, and the message says whether it was created or already existed, with the full path. For the default folder it also says that it sits next to the scanned folder, not inside it.
- If the folder cannot be created (permissions, bad path) the tool says why and asks for another location instead of failing later.
- At the end of a guided run on Windows it prints the output folder path and offers to open it in Explorer.
- `--undo` no longer creates an empty output folder when it does not exist; it only reports where it looked for the log.
- Files Changed: `phash_dedupe.py`, `README.md`, `CHANGELOG.md`.

## v2.4 - Prompt and title wording
**Date:** 21-11-2026

- Yes/no questions now read `[Y/N, Enter = Yes]` or `[Y/N, Enter = No]` instead of `[Y/n]` and `[y/N]`.
- The guided-mode heading is now "Duplicate image finder" (sentence case, without the file name). The status report heading and the launcher window title follow the same wording.
- Launcher install question shows `[Y/N]` instead of `[Y,N]`.
- Files Changed: `phash_dedupe.py`, `run_phash_dedupe.bat`, `CHANGELOG.md`.

## v2.3 - Windows launcher
**Date:** 21-11-2026

- Added `run_phash_dedupe.bat`. Double-click for the guided mode, drag folders onto it, or pass any `phash_dedupe.py` options after it.
- Finds Python automatically (local `phash-env` virtual environment, then `py -3`, then `python`) and shows a clear message if none works.
- Checks that `imagehash`, `pillow` and `numpy` are installed and offers to install them.
- Does not change the current folder, so "Enter = current folder" in the questions is the folder it was started from. Sets UTF-8 output so folder names in other scripts display correctly.
- Keeps the window open when started with arguments (the guided mode already waits for Enter).
- No change to `phash_dedupe.py`.
- Files Changed: `run_phash_dedupe.bat`, `README.md`, `CHANGELOG.md`.

## v2.2 - Confirmation of folders and file counts
**Date:** 21-11-2026

- Confirmation 1, after scanning and before hashing: lists every folder with its image count and the total, then asks whether to continue (default yes).
- Confirmation 2, after duplicates are found and before moving (`--apply`): lists every folder with its image count and the number of copies that will be moved from it, the total and the destination, then asks whether to move (default no). A dry run shows the same table without asking.
- Declining stops the run, moves nothing and sets the status report to `CANCELLED`.
- Questions are asked in the guided mode and when the CLI is run from a terminal. New `--yes` / `-y` skips them for scripts. The old generic "this will move files" question in the guided mode is replaced by confirmation 2, which has the real numbers.
- Status report gets a `FOLDERS AFFECTED` section (images and copies per folder) and a `WAITING FOR YOUR CONFIRMATION` state. Time spent waiting is not counted in the elapsed time.
- Files Changed: `phash_dedupe.py`, `README.md`, `CHANGELOG.md`.

## v2.1 - Multiple folders and nested folder option
**Date:** 21-11-2026

- Scan several folders in one run: pass more than one path on the command line, or keep adding folders in the guided questions (Enter on an empty line finishes; several quoted paths on one line also work).
- All folders are hashed and grouped together, so duplicates across different folders are found. The original is chosen by the usual rule across folders.
- Nested subfolders are included by default and processed like the top level. New `--no-subfolders` option (and a guided question) limits the scan to the top level of each folder.
- Repeated folders are ignored and a folder already inside another selected folder is skipped with a note, so no image is processed twice.
- Mode `output` with several folders puts copies in one subfolder per scanned folder (`copies\<folder name>\...`, same names become `name_2`). A single folder keeps the v2.0 layout.
- Default output folder for several folders: `multi_<N>_folders_dedupe_output` in the common parent of the folders (first folder's parent if they are on different drives).
- Status report lists every scanned folder, whether subfolders are included, and the number of folders scanned. `--undo` accepts several folders.
- Files Changed: `phash_dedupe.py`, `README.md`, `CHANGELOG.md`.

## v2.0 - Guided mode, output folder and live status report
**Date:** 21-11-2026

- Runs from any folder. With no path given the script asks questions: find duplicates or undo, folder to scan (Enter = current folder), output folder, copies mode, threshold, preview or move. Passing a path still works exactly like before with no questions.
- Output folder: the user can select one by typing its location, or let the script create `<scanned folder name>_dedupe_output` next to the scanned folder in its parent folder. New `--output` option for the command line. If the scanned folder is a drive root the default is `_dedupe_output` inside it.
- New default mode `output`: copies go to `<output>\copies\` with the same subfolder structure. `own` and `original` modes are unchanged and can still be chosen.
- Live status report `status_report.txt` in the output folder, refreshed every second and written atomically: overall progress bar, items done, items remaining, speed, time remaining with expected finish time, a four-step checklist with timings, skipped files and a final result summary. Also shows `INTERRUPTED` after Ctrl+C and `FAILED` with the error. One live progress line is shown in the console.
- Move log `phash_moves_log.csv` now lives in the output folder and each move is written immediately, so `--undo` works after an interrupted run. `--undo` also finds v1.x logs in the scanned folder, removes empty `copies` folders and accepts `--output`.
- The output folder is skipped when it sits inside the scanned folder.
- Dry run now reserves destination names, so two copies with the same file name show distinct targets (`name_1.ext`).
- A failed move is reported and counted instead of stopping the run.
- Changed default: `--mode` is now `output` (was `own`). Use `--mode own` for the old behaviour.
- Files Changed: `phash_dedupe.py`, `README.md`, `CHANGELOG.md`.

## v1.1 - README and changelog added
**Date:** 21-11-2026

- Added `README.md` and `CHANGELOG.md` in the same format as the LDE website documentation: what it is, folder layout, command options, how duplicates are handled, usage steps, maintenance notes, a pre-run checklist and a tech stack table.
- Documented the threshold guide, the two modes with a worked path example, the known limitations and the constants (`EXTS`, `COPIES`, `LOG_NAME`) that can be edited at the top of the script.
- No change to the script itself.
- Files Changed: `README.md`, `CHANGELOG.md`.

## v1.0 - First version
**Date:** 21-11-2026

- Recursive scan of nested folder trees for `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tif` and `.tiff`.
- Perceptual hashing with `imagehash.phash`, configurable with `--hash-size` (8 = 64-bit, 16 = 256-bit).
- Duplicate grouping by Hamming distance with `--threshold` (default 6).
- Original selection rule: highest resolution, then largest file size, then oldest modified date, then shortest path.
- Greedy grouping that compares copies against the original only, so chains of slightly different images do not merge.
- `--mode own` (default) moves each copy into a `copies` folder inside its current folder. `--mode original` moves it into a `copies` folder next to the image it duplicates.
- Dry run by default. Files only move with `--apply`, and nothing is deleted.
- Move log `phash_moves_log.csv` in the scanned root (original path, new path, matched original, distance) and `--undo` to restore from it.
- Name clash handling (`name_1.ext`, `name_2.ext`) and automatic skipping of existing `copies` folders so re-runs are safe.
- Corrupt or unreadable images are reported and skipped. Progress is printed every 500 images.
- Known limits: rotated, mirrored or heavily cropped copies are not detected; comparison is O(n²); GIFs and multi-page TIFFs use the first frame only; no video or audio support.
- Files Changed: `phash_dedupe.py`.
