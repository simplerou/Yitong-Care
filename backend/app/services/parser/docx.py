from io import BytesIO
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring

from app.services.parser.text import ParseError, normalize_text

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(data: bytes) -> str:
    """按 WordprocessingML 顺序提取主文档段落及表格文字。"""
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 128 * 1024 * 1024:
                raise ParseError("DOCX 解压内容过大，请简化或拆分文档。")
            if any(e.flag_bits & 1 for e in entries):
                raise ParseError("暂不支持加密 DOCX，请解密后上传。")
            xml = archive.read("word/document.xml")
        root = fromstring(xml)
        if root.tag != W + "document":
            raise ParseError("不是有效的 Word DOCX 文档。")
        lines = []
        for paragraph in root.iter(W + "p"):
            fragments = []
            for element in paragraph.iter():
                if element.tag == W + "t":
                    fragments.append(element.text or "")
                elif element.tag == W + "tab":
                    fragments.append("\t")
                elif element.tag in {W + "br", W + "cr"}:
                    fragments.append("\n")
            lines.append("".join(fragments))
        return normalize_text("\n".join(lines))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("DOCX 已损坏或格式不正确，请另存为 .docx 后上传。") from exc
