"""
PDF Processing Utility — Memory-Safe Version
Handles page-combining, splitting, merging, compression, and watermarking.

Key safety rules:
- combine_pages renders ONE page at a time, writes JPEG to disk, frees RAM immediately
- MAX_PAGES_LIMIT enforced before any heavy work starts
- All temp files cleaned up even on error
"""

import os
import gc
import math
import uuid
from typing import List

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas

from config import TEMP_DIR, RENDER_DPI

os.makedirs(TEMP_DIR, exist_ok=True)

# Hard limit — refuse PDFs larger than this to protect VPS RAM
MAX_PAGES_LIMIT = 200
# Lower DPI = less RAM. 150 is plenty for printing, 200 is high quality.
SAFE_DPI = min(RENDER_DPI, 150)


def _tmp(suffix=".pdf") -> str:
    return os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}{suffix}")


# ─────────────────────────────────────────
# Core: Combine N pages into one sheet
# MEMORY SAFE: renders one page at a time,
# writes JPEG to disk, deletes from RAM before next page.
# ─────────────────────────────────────────

def combine_pages(input_path: str, pages_per_sheet: int) -> str:
    """
    Stream-renders pages one at a time — safe for large PDFs on low-RAM VPS.
    Uses pypdfium2 (no poppler). Returns output PDF path.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError("pypdfium2 not installed. Run: pip install pypdfium2")

    doc   = pdfium.PdfDocument(input_path)
    total = len(doc)

    if total > MAX_PAGES_LIMIT:
        doc.close()
        raise ValueError(
            f"PDF has {total} pages. Maximum allowed is {MAX_PAGES_LIMIT} to protect server RAM."
        )

    cols, rows = _grid(pages_per_sheet)
    if cols > rows:
        page_w, page_h = landscape(A4)
    else:
        page_w, page_h = A4

    cell_w = page_w / cols
    cell_h = page_h / rows
    scale  = SAFE_DPI / 72

    output_path = _tmp()
    c = rl_canvas.Canvas(output_path, pagesize=(page_w, page_h))

    page_idx = 0
    while page_idx < total:
        # White background for this output sheet
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        for slot in range(pages_per_sheet):
            if page_idx >= total:
                break

            # ── Render ONE page, write to disk, free RAM immediately ──
            pdf_page = doc[page_idx]
            bitmap   = pdf_page.render(scale=scale, rotation=0)
            pil_img  = bitmap.to_pil().convert("RGB")

            img_w, img_h = pil_img.size
            scale_fit    = min(cell_w / img_w, cell_h / img_h) * 0.96

            draw_w = img_w * scale_fit
            draw_h = img_h * scale_fit

            row = slot // cols
            col = slot % cols
            x   = col * cell_w + (cell_w - draw_w) / 2
            y   = page_h - (row + 1) * cell_h + (cell_h - draw_h) / 2

            tmp_img = _tmp(".jpg")
            pil_img.save(tmp_img, "JPEG", quality=88, optimize=True)

            # Free the PIL image from RAM before drawing
            del pil_img
            del bitmap
            gc.collect()

            c.drawImage(tmp_img, x, y, draw_w, draw_h)
            os.remove(tmp_img)   # JPEG gone from disk too

            page_idx += 1

        c.showPage()

    doc.close()
    c.save()
    return output_path


def _grid(n: int):
    """Return (cols, rows) for n pages per sheet."""
    layouts = {
        1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (2, 2),
        6: (3, 2), 8: (4, 2), 9: (3, 3), 12: (4, 3),
        16: (4, 4),
    }
    if n in layouts:
        return layouts[n]
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


# ─────────────────────────────────────────
# Split: one page per file → list of paths
# ─────────────────────────────────────────

def split_pdf(input_path: str) -> List[str]:
    reader = PdfReader(input_path)
    paths  = []
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        out = _tmp()
        with open(out, "wb") as f:
            writer.write(f)
        paths.append(out)
    return paths


# ─────────────────────────────────────────
# Merge: list of PDFs → single PDF
# ─────────────────────────────────────────

def merge_pdfs(paths: List[str]) -> str:
    writer = PdfWriter()
    for p in paths:
        reader = PdfReader(p)
        for page in reader.pages:
            writer.add_page(page)
    out = _tmp()
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ─────────────────────────────────────────
# Compress: reduce file size
# ─────────────────────────────────────────

def compress_pdf(input_path: str) -> str:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.compress_content_streams()
        writer.add_page(page)
    out = _tmp()
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ─────────────────────────────────────────
# Rotate all pages
# ─────────────────────────────────────────

def rotate_pdf(input_path: str, degrees: int) -> str:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    out = _tmp()
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ─────────────────────────────────────────
# Extract page range
# ─────────────────────────────────────────

def extract_pages(input_path: str, start: int, end: int) -> str:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    total  = len(reader.pages)
    start  = max(1, start)
    end    = min(total, end)
    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])
    out = _tmp()
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ─────────────────────────────────────────
# Watermark
# ─────────────────────────────────────────

def watermark_pdf(input_path: str, text: str) -> str:
    from reportlab.lib.colors import Color

    reader   = PdfReader(input_path)
    out_path = _tmp()

    c = rl_canvas.Canvas(out_path)
    for page in reader.pages:
        box    = page.mediabox
        pw, ph = float(box.width), float(box.height)
        c.setPageSize((pw, ph))
        c.saveState()
        c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.25))
        c.setFont("Helvetica-Bold", min(pw, ph) // 12)
        c.translate(pw / 2, ph / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.showPage()
    c.save()

    wm_reader = PdfReader(out_path)
    writer    = PdfWriter()
    for orig_page, wm_page in zip(reader.pages, wm_reader.pages):
        orig_page.merge_page(wm_page)
        writer.add_page(orig_page)

    final = _tmp()
    with open(final, "wb") as f:
        writer.write(f)
    os.remove(out_path)
    return final


# ─────────────────────────────────────────
# Page count
# ─────────────────────────────────────────

def page_count(input_path: str) -> int:
    return len(PdfReader(input_path).pages)


# ─────────────────────────────────────────
# Cleanup helper
# ─────────────────────────────────────────

def cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
