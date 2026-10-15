"""The CV's page images: one rasteriser at a time, cached, and never a 500.

PDFium — which pdfplumber rasterises with — is not thread-safe, and the *Archivo original*
pane asks for page 1 and page 2 at the same moment; FastAPI answers both in its thread
pool. These tests pin what the operator's *Data format error* cost: the rasterisers are
serialised, a page the renderer cannot draw is a 404 rather than a 500, and a page already
rendered is not rendered again.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pdfplumber
import pytest
from pdfplumber.utils.exceptions import MalformedPDFException
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.resumes import create_resume
from src.web import locations
from src.web.routes import analyze as analyze_routes
from tests.conftest import login
from tests.unit.cv_support import draft_dict
from tests.unit.test_analysis import store_flagged

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def bytes_of(number: int) -> bytes:
    """Distinct file bytes for the cache tests, one per `number`."""
    return f"%PDF-fake-{number}".encode()


@pytest.fixture(autouse=True)
def _an_empty_cache():
    """The cache lives in the process; every test starts and ends with it empty."""
    locations._PAGE_CACHE.clear()
    yield
    locations._PAGE_CACHE.clear()


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
        locations._PAGE_CACHE.clear()  # every round rasterises all eight
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


def test_a_page_already_rendered_is_not_rasterised_again(monkeypatch):
    """A reload of the report — or the pane's second request — reads a PNG, not the file."""
    opened: list[int] = []
    real_open = pdfplumber.open

    def counting_open(*args, **kwargs):
        opened.append(1)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(locations.pdfplumber, "open", counting_open)
    data = two_page_pdf()

    first = locations.render_page_png(data, page_number=2, boxes=[], severity="info")
    again = locations.render_page_png(data, page_number=2, boxes=[], severity="info")

    assert first == again
    assert len(opened) == 1, "the second render came from the cache"


def test_a_boxed_render_never_serves_the_plain_page():
    """The key carries the boxes and the colour: two views of one page are two images."""
    data = two_page_pdf()

    plain = locations.render_page_png(data, page_number=1, boxes=[], severity="info")
    boxed = locations.render_page_png(
        data, page_number=1, boxes=[(60, 60, 300, 90)], severity="blocker"
    )

    assert boxed != plain, "the finding's boxes are drawn, not the pane's bare page"
    assert boxed.startswith(PNG_SIGNATURE)


def test_the_cache_is_capped_and_evicts_the_least_recently_used(monkeypatch):
    """A long session cannot grow the cache: 32 views, and the oldest unused one goes."""
    drawn: list[bytes] = []

    def stub(data: bytes, **_kwargs) -> bytes:
        drawn.append(data)
        return PNG_SIGNATURE + data

    monkeypatch.setattr(locations, "_draw_page", stub)

    def render(number: int) -> bytes:
        return locations.render_page_png(
            bytes_of(number), page_number=1, boxes=[], severity="info"
        )

    for number in range(1, locations.PAGE_CACHE_SIZE + 1):
        render(number)
    render(1)
    render(locations.PAGE_CACHE_SIZE + 1)

    assert len(locations._PAGE_CACHE) == locations.PAGE_CACHE_SIZE
    render(1)
    assert drawn.count(bytes_of(1)) == 1, "the view used again is still cached"
    render(2)
    assert drawn.count(bytes_of(2)) == 2, "the view untouched longest was the one evicted"


# --- the route ---


def stored_report_on_a_cv(session, career, *, pages: int = 2):
    """A stored report on a PDF CV: the file's real bytes, no model call."""
    resume = create_resume(
        career.first_profile.id,
        session,
        filename="cv.pdf",
        data=two_page_pdf(pages),
        sha256=hashlib.sha256(b"page-images").hexdigest(),
        track_id=career.first_track.id,
        gate=None,
        draft=draft_dict(career.first_bullet.text_es),
    )
    application = store_flagged(
        session, career.first_profile.id, capped=40, uncapped=62, cap=40, severity="blocker"
    )
    application.resume_id = resume.id
    application.report = {
        **application.report,
        "cv": {"resume_id": str(resume.id), "filename": "cv.pdf", "chosen": "explicit"},
    }
    session.commit()
    return application, resume


def test_a_renderer_that_fails_is_a_404_and_one_warning(
    client, session, career, monkeypatch, caplog
):
    """The operator's *Data format error*: no image of that page, never a 500."""
    application, _resume = stored_report_on_a_cv(session, career)
    login(client, career.first.email)

    def failing(*_args, **_kwargs) -> bytes:
        raise MalformedPDFException("Failed to load document (PDFium: Data format error).")

    monkeypatch.setattr(analyze_routes, "render_page_png", failing)
    caplog.set_level(logging.WARNING)

    answer = client.get(f"/applications/{application.id}/cv/page/1.png")

    assert answer.status_code == 404
    assert f"application={application.id}" in caplog.text
    assert "page=1" in caplog.text
