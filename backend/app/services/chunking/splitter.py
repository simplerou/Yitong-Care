import re

from app.schemas.chunk import ChunkParameters, ChunkRead, ChunkResult


def split_text(doc_id: str, text: str, parameters: ChunkParameters) -> ChunkResult:
    """片段始终是原文的连续子串，保留准确字符位置；重叠只回退完整句。"""
    units: list[tuple[int, int]] = []
    for match in re.finditer(r".+?(?:[。！？；\n]+|$)", text, flags=re.DOTALL):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        while start < end:
            stop = min(start + parameters.size, end)
            units.append((start, stop))
            start = stop
    chunks: list[ChunkRead] = []
    i = 0
    previous_end = 0
    while i < len(units):
        start, end = units[i]
        j = i + 1
        while j < len(units) and units[j][1] - start <= parameters.size:
            end = units[j][1]
            j += 1
        content = text[start:end]
        chunks.append(ChunkRead(
            doc_id=doc_id, seq=len(chunks) + 1, content=content,
            start_offset=start, chars=len(content),
            overlap_chars=max(0, previous_end - start),
        ))
        previous_end = end
        next_i = j
        if j < len(units) and parameters.overlap:
            while next_i > i + 1 and end - units[next_i - 1][0] <= parameters.overlap:
                next_i -= 1
        # 重叠不能挤占下一句空间，否则直接前进，避免重复或超长。
        if next_i < j and units[j][1] - units[next_i][0] > parameters.size:
            next_i = j
        i = next_i
    return ChunkResult(
        doc_id=doc_id, count=len(chunks),
        average_chars=round(sum(c.chars for c in chunks) / len(chunks)) if chunks else 0,
        chunks=chunks,
    )
