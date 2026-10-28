class ParseError(ValueError):
    """可安全展示给用户的解析错误。"""


MAX_TEXT_CHARS = 2_000_000


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    if not text:
        raise ParseError("未提取到正文。扫描版 PDF 暂需先做 OCR，或上传文字版文档。")
    if len(text) > MAX_TEXT_CHARS:
        raise ParseError("正文超过 200 万字符，请拆分文档后上传。")
    return text


def parse_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"]
    else:
        if b"\x00" in data:
            raise ParseError("文件不像纯文本，请确认文件格式。")
        encodings = ["utf-8-sig", "gb18030"]
    for encoding in encodings:
        try:
            return normalize_text(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise ParseError("无法识别文本编码，请另存为 UTF-8 后上传。")
