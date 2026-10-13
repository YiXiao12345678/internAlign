from pathlib import Path
from pypdf import PdfReader


def extract_resume_text(file_path: str) -> str:
    """
    Extract text from a PDF resume.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("The resume must be a PDF file.")

    reader = PdfReader(str(path))

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(page_text)

    return "\n\n".join(pages).strip()
