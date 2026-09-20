"""Loading an upload into text and a gate report (PRD F2.1/F2.2).

The gate runs on the same parse the model gets, bytes first: an upload the ATS
cannot read is a fact shown before any extracted content, and the file is archived
unchanged either way (F2.6).
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from src.parse.docx import read_docx
from src.parse.gate import ParseReport, check_document, check_docx
from src.parse.pdf import read_pdf

SUPPORTED_SUFFIXES = (".pdf", ".docx")


class UnsupportedDocument(ValueError):
    """Not a PDF or a DOCX. Named so the UI can say which formats are accepted."""


class UnreadableDocument(ValueError):
    """The reader refused the bytes: corrupt, truncated, or not really that format."""


@dataclass(frozen=True)
class LoadedDocument:
    kind: str  # "pdf" | "docx"
    text: str
    gate: ParseReport


def normalize_document_text(text: str) -> str:
    """Collapse what does not change meaning, keeping the document's lines.

    Line structure carries the bullets, so unlike a job posting this normalisation
    keeps newlines; it only unifies newline styles, hard spaces and runs of spaces,
    which is what makes a re-upload of the same document hit the same cache entry.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [" ".join(line.split()) for line in unified.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def load_document(filename: str, data: bytes) -> LoadedDocument:
    """Text and findings for a PDF or DOCX upload, or a named refusal."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocument(suffix or filename)
    try:
        if suffix == ".pdf":
            document = read_pdf(BytesIO(data))
            return LoadedDocument(
                kind="pdf",
                text=normalize_document_text(document.text),
                gate=check_document(document),
            )
        document = read_docx(BytesIO(data))
        return LoadedDocument(
            kind="docx",
            text=normalize_document_text(document.text),
            gate=check_docx(document),
        )
    except Exception as exc:  # noqa: BLE001
        # The readers raise from several libraries (pdfminer, python-docx, zipfile)
        # and every one of them means the same thing to the user: this file cannot
        # be read. Named here so the route never has to know which library spoke.
        raise UnreadableDocument(str(exc)) from exc