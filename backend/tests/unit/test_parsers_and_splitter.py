from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter

from app.schemas.chunk import ChunkParameters
from app.services.chunking.splitter import split_text
from app.services.parser.docx import parse_docx
from app.services.parser.pdf import parse_pdf
from app.services.parser.text import ParseError, parse_text


def test_text_encodings_and_binary_rejection():
    for encoding in ['utf-8-sig', 'utf-16', 'gb18030']:
        assert parse_text('社区服务\r\n窗口咨询'.encode(encoding)) == '社区服务\n窗口咨询'
    with pytest.raises(ParseError):
        parse_text(b'\x00\x01binary')


def test_scanned_pdf_and_docx_entity_rejection():
    pdf = PdfWriter(); pdf.add_blank_page(width=100, height=100)
    stream = BytesIO(); pdf.write(stream)
    with pytest.raises(ParseError, match='OCR'):
        parse_pdf(stream.getvalue())
    stream = BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', '<!DOCTYPE x [<!ENTITY boom "test">]><x>&boom;</x>')
    with pytest.raises(ParseError):
        parse_docx(stream.getvalue())


def test_offsets_repeat_text_size_and_progress():
    text = '\n  ' + '重复句子。' * 80 + '\n' + '很长的正文' * 40
    result = split_text('d', text, ChunkParameters(size=100, overlap=30))
    assert result.count > 1
    previous_start = -1
    covered = set()
    for chunk in result.chunks:
        assert chunk.start_offset > previous_start
        assert chunk.content == text[chunk.start_offset:chunk.start_offset + chunk.chars]
        assert 0 < chunk.chars <= 100
        assert 0 <= chunk.overlap_chars <= 30
        covered.update(range(chunk.start_offset, chunk.start_offset + chunk.chars))
        previous_start = chunk.start_offset
    assert all(i in covered for i, char in enumerate(text) if not char.isspace())
    assert split_text('empty', '   ', ChunkParameters()).count == 0


def test_text_pdf_extracts_its_actual_content():
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 40 150 Td (Community service document) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    output = BytesIO(); writer.write(output)
    assert parse_pdf(output.getvalue()) == 'Community service document'
