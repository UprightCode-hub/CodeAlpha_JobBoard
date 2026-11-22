"""Builders for valid and deliberately broken resume files (test support only).

Not a test module (no ``test`` prefix), so Django will not collect it.
"""

import io
import zipfile

from pypdf import PdfWriter

MAX_BYTES = 2 * 1024 * 1024

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MAIN_DOC_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)

CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    f'<Override PartName="/word/document.xml" ContentType="{MAIN_DOC_TYPE}"/>'
    "</Types>"
).encode()

RELS_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" '
    b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    b'relationships/officeDocument" '
    b'Target="word/document.xml"/>'
    b"</Relationships>"
)

DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{W_NS}"><w:body>'
    "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
    "</w:body></w:document>"
).encode()


# ---------------------------------------------------------------- PDF


def valid_pdf_bytes(pages=1, padding=0):
    """A structurally valid PDF with ``pages`` blank pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if padding:
        writer.add_metadata({"/Padding": "x" * padding})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def zero_page_pdf_bytes():
    """A PDF with no pages, or None if pypdf refuses to write one."""
    writer = PdfWriter()
    buffer = io.BytesIO()
    try:
        writer.write(buffer)
    except Exception:  # noqa: BLE001 - pypdf version dependent
        return None
    return buffer.getvalue()


def pdf_of_size(target):
    """A valid PDF whose length is exactly ``target`` bytes."""
    padding = max(target - len(valid_pdf_bytes()), 1)
    for _ in range(10):
        data = valid_pdf_bytes(padding=padding)
        difference = target - len(data)
        if difference == 0:
            return data
        padding += difference
    raise AssertionError(f"could not build a valid PDF of exactly {target} bytes")


# ---------------------------------------------------------------- DOCX


def docx_parts():
    """Fresh dict of the minimal valid DOCX parts (mutate, then zip_bytes())."""
    return {
        "[Content_Types].xml": CONTENT_TYPES_XML,
        "_rels/.rels": RELS_XML,
        "word/document.xml": DOCUMENT_XML,
    }


def zip_bytes(parts, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as package:
        for name, content in parts.items():
            package.writestr(name, content)
    return buffer.getvalue()


def valid_docx_bytes(compression=zipfile.ZIP_DEFLATED):
    return zip_bytes(docx_parts(), compression)
