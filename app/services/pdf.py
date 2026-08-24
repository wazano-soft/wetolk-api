import logging
import threading
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


class UnextractableTextError(Exception):
    """El PDF no tiene texto extraíble (probable escaneo sin OCR) — RF-02."""


def extract_text(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        text = "\n".join(page.get_text() for page in doc).strip()
    finally:
        doc.close()

    if not text:
        raise UnextractableTextError()
    return text


_WATERMARK_PATH = Path(__file__).resolve().parent.parent / "assets" / "watermark.png"
_WATERMARK_OPACITY = 0.18


def _load_watermark_pixmap() -> pymupdf.Pixmap | None:
    # Precomputado una sola vez a nivel de módulo -- source es un PNG de
    # 1800x1800 (logo-square.png del frontend), muy por encima de lo que
    # necesita una marca de agua sutil. shrink(3) lo baja a ~225x225 antes
    # de aplicar la opacidad: insertar el pixmap crudo en el PDF escala su
    # peso con el cuadrado de la resolución, así que sin este shrink cada
    # CV descargado pesaba +800KB solo por la marca de agua.
    #
    # Si falta el asset (o está corrupto), esto NO puede tumbar el boot de
    # toda la API -- pdf.py se importa transitivamente desde main.py, así
    # que una excepción acá arriba de todo dejaba el proceso entero sin
    # levantar por un logo faltante. Se degrada a "sin marca de agua" en
    # vez de crashear.
    try:
        pix = pymupdf.Pixmap(str(_WATERMARK_PATH))
    except Exception:
        logger.warning("Could not load watermark asset at %s -- CV downloads won't be watermarked", _WATERMARK_PATH)
        return None
    if not pix.alpha:
        pix = pymupdf.Pixmap(pix, 1)
    pix.shrink(3)
    alpha_byte = int(255 * _WATERMARK_OPACITY)
    pix.set_alpha(bytes([alpha_byte]) * (pix.width * pix.height))
    return pix


_watermark_pixmap = _load_watermark_pixmap()
# MuPDF (la librería de base de pymupdf) no garantiza ser thread-safe para
# uso concurrente del mismo objeto Pixmap desde threads distintos --
# download_public_cv es una ruta sync, así que FastAPI la despacha en el
# threadpool. Este lock serializa solo la inserción de la imagen (rápida),
# no el resto del procesamiento del PDF.
_watermark_lock = threading.Lock()


def add_watermark(pdf_bytes: bytes) -> bytes:
    if _watermark_pixmap is None:
        return pdf_bytes

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        xref = None
        with _watermark_lock:
            for page in doc:
                rect = page.rect
                side = min(rect.width, rect.height) * 0.5
                cx, cy = rect.width / 2, rect.height / 2
                wm_rect = pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
                if xref is None:
                    # Primera página: embebe el pixmap. Páginas siguientes
                    # reusan el mismo xref en vez de re-embeberlo -- sin
                    # esto, cada página sumaba de nuevo el peso crudo de
                    # la imagen.
                    xref = page.insert_image(wm_rect, pixmap=_watermark_pixmap, overlay=True)
                else:
                    page.insert_image(wm_rect, xref=xref, overlay=True)
        return doc.tobytes(deflate=True, garbage=4)
    finally:
        doc.close()
