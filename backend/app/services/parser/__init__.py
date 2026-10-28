from pathlib import Path

from app.services.parser.docx import parse_docx
from app.services.parser.pdf import parse_pdf
from app.services.parser.text import parse_text


def parse_file(path: Path, file_type: str) -> str:
    data = path.read_bytes()
    parser = {"PDF": parse_pdf, "DOCX": parse_docx}.get(file_type, parse_text)
    return parser(data)
