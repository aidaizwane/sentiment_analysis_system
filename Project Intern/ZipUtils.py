import os
import zipfile

SUPPORTED_IN_ZIP = (".wav", ".mp3", ".m4a", ".pdf", ".docx", ".txt")

def safe_extract_zip(zip_path: str, extract_to: str) -> list[str]:
    """
    Extract zip safely (avoid zip-slip). Returns list of extracted file paths (supported only).
    """
    extracted_files = []

    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue

            name = member.filename

            if not name.lower().endswith(SUPPORTED_IN_ZIP):
                continue

            dest_path = os.path.abspath(os.path.join(extract_to, name))
            base_path = os.path.abspath(extract_to)
            if not dest_path.startswith(base_path + os.sep):
                continue

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            with z.open(member) as src, open(dest_path, "wb") as dst:
                dst.write(src.read())

            extracted_files.append(dest_path)

    return extracted_files
