from io import BytesIO

from pypdf import PdfReader

from app.services.parser.text import ParseError, normalize_text


def parse_pdf(data: bytes) -> str:
    if not data.lstrip().startswith(b"%PDF-"):
        raise ParseError("文件内容不是有效的 PDF。")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("暂不支持加密 PDF，请解密后上传。")
        if len(reader.pages) > 1000:
            raise ParseError("PDF 超过 1000 页，请拆分后上传。")
        pages = []
        length = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            length += len(text)
            if length > 2_000_000:
                raise ParseError("正文超过 200 万字符，请拆分文档后上传。")
            pages.append(text)
        return normalize_text("\n".join(pages))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("PDF 已损坏或无法解析，请检查原文件。") from exc
