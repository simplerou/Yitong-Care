"""Expand ranked hits to a bounded, exact source substring; ranking is unchanged."""
import re


def expand_hit(hit, document, budget=4000, margin=600):
    body = document.content or ''
    start, end = hit.start, hit.end
    # Refuse to invent offsets when parsed content has changed or is unavailable.
    if not body or body[start:end] != hit.text or len(hit.text) > budget:
        return hit
    left = max(0, start-margin)
    right = min(len(body), end+margin)
    if right-left > budget:
        left = max(left, start-min(margin, (budget-(end-start))//2))
        right = min(right, left+budget)
    headings = list(re.finditer(r'(?m)^(?:#{1,6}\s+[^\n]{1,120}|第[一二三四五六七八九十百0-9]+[章节条][^\n]{0,100}|[一二三四五六七八九十]+、[^\n]{1,100})$', body[:start]))
    heading = headings[-1].group(0) if headings else None
    # Heading is navigation context, not a fabricated prefix inside quoted evidence.
    return hit.model_copy(update=dict(text=body[left:right], start=left, end=right, chars=right-left,
        matched_start=start, matched_end=end, context_expanded=left!=start or right!=end, heading=heading))
