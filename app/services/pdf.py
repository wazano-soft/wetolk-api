import pymupdf


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
