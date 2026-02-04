import os
import tempfile

from ZipUtils import safe_extract_zip
from Utils import detect_file_type
from AudioProcessing import process_single_audio_file
from TextProcessing import process_single_text_file


def process_zip_upload(zip_path: str) -> dict:
    """
    Extract ZIP LOCALLY (no Gemini)
    Then process extracted files one by one.
    """
    if not os.path.exists(zip_path):
        return {"success": False, "error": f"ZIP not found: {zip_path}"}

    processed = 0
    failed = 0
    results = []

    with tempfile.TemporaryDirectory() as tmp:
        extracted_files = safe_extract_zip(zip_path, tmp)

        if not extracted_files:
            return {"success": False, "error": "No supported files inside ZIP"}

        # Sort: text first then audio (optional)
        def sort_key(path: str):
            t = detect_file_type(path)
            return 0 if t == "text" else 1

        extracted_files.sort(key=sort_key)

        for file_path in extracted_files:
            try:
                ftype = detect_file_type(file_path)

                if ftype == "audio":
                    r = process_single_audio_file(file_path)
                elif ftype == "text":
                    r = process_single_text_file(file_path)
                else:
                    continue

                results.append(r)
                if r.get("success"):
                    processed += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                results.append({"success": False, "file": file_path, "error": str(e)})

    return {
        "success": True,
        "processed": processed,
        "failed": failed,
        "total": len(results),
        "results": results,
    }
