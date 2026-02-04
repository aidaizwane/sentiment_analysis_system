import time
import tempfile
from pathlib import Path

from AudioProcessing import process_single_audio_file
from TextProcessing import process_single_text_file
from Utils import detect_file_type
from ZipUtils import safe_extract_zip

LOCAL_INPUT_PATH = r"C:\Users\W10\Documents\Audio Test Folder"

TEXT_DELAY_SECONDS = 2
AUDIO_DELAY_SECONDS = 10

def _process_one_local_file(file_path: Path):
    ftype = detect_file_type(file_path.name)

    if ftype == "audio":
        print(f"\n[PROCESS] AUDIO -> {file_path}")
        process_single_audio_file(str(file_path))
        time.sleep(AUDIO_DELAY_SECONDS)

    elif ftype == "text":
        print(f"\n[PROCESS] TEXT  -> {file_path}")
        process_single_text_file(str(file_path))
        time.sleep(TEXT_DELAY_SECONDS)


def process_all_files_once():
    base_path = Path(LOCAL_INPUT_PATH)

    if not base_path.exists():
        print(f"[ERROR] Folder not found: {base_path}")
        return

    print(f"[INFO] Processing LOCAL folder: {base_path}")

    files = []

    for item in base_path.rglob("*"):
        if not item.is_file():
            continue

        if item.suffix.lower() == ".zip":
            files.append(item)
        else:
            ftype = detect_file_type(item.name)
            if ftype in ("audio", "text"):
                files.append(item)

    if not files:
        print("[INFO] No supported files found.")
        return

    def sort_key(p: Path):
        if p.suffix.lower() == ".zip":
            return 2
        return 0 if detect_file_type(p.name) == "text" else 1

    files.sort(key=sort_key)

    print(f"[INFO] Found {len(files)} file(s). Starting processing...\n")

    for f in files:
        try:
            if f.suffix.lower() == ".zip":
                print(f"\n[PROCESS] ZIP   -> {f.name}")
                with tempfile.TemporaryDirectory() as tmp:
                    extracted = safe_extract_zip(str(f), tmp)

                    if not extracted:
                        print(f"[INFO] No supported files inside ZIP: {f.name}")
                        continue

                    extracted.sort(key=lambda p: 0 if detect_file_type(p) == "text" else 1)

                    for ef in extracted:
                        _process_one_local_file(Path(ef))
            else:
                _process_one_local_file(f)

        except Exception as e:
            print(f"[ERROR] Failed processing {f}: {e}")

    print("\n[DONE] Local folder processing completed.")
