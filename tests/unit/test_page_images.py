"""The CV's page images: one rasteriser at a time.

PDFium — which pdfplumber rasterises with — is not thread-safe, and the *Archivo original*
pane asks for page 1 and page 2 at the same moment; FastAPI answers both in its thread
pool. This pins the first promise: the rasterisers are serialised, so the two loads never
run into each other.
"""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.web import locations

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def two_page_pdf(pages: int = 2) -> bytes:
    """A real PDF of `pages` pages of selectable text — what PDFium has to load."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    for number in range(1, pages + 1):
        pdf.setFont("Helvetica", 11)
        pdf.drawString(60, 720, f"Página {number}: analista de datos con Python")
        pdf.drawString(60, 700, "Acme · 2021-2024 · reportes y tableros")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# --- the rasteriser ---


def test_eight_threads_render_both_pages_at_once_three_times():
    """The pane's two requests arrive together; PDFium is called from one thread only."""
    data = two_page_pdf()

    for _round in range(3):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(
                    locations.render_page_png,
                    data,
                    page_number=1 + index % 2,
                    boxes=[],
                    severity="info",
                )
                for index in range(8)
            ]
            pages = [future.result(timeout=120) for future in futures]

        assert len(pages) == 8
        assert all(page.startswith(PNG_SIGNATURE) for page in pages)
