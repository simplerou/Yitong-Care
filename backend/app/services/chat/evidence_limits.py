"""Conservative scope checks: extracted text is never proof of full-document coverage."""
import re
import unicodedata


def compact(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))


def evidence_scope_issues(text, evidence):
    support='\n'.join(item['text'] for item in evidence)
    issues=[]
    for sentence in re.split(r'[。！？\n]',text):
        # Explicitly qualified observations about a fragment do not claim full coverage.
        fragment=bool(re.search(r'摘录|片段|截取',sentence))
        uncertain=bool(re.search(r'不能|无法|不足以|不代表|尚不能|不能据此|并非|不是|并不|不意味着',sentence))
        absence=bool(re.search(r'(?:目录|清单|全文|文件|附件|名单|政策).{0,120}(?:未列明|未列入|未包含|未收录|不存在|未提及|未载明|没有列入|没有包含|没有提及)',sentence)
                     or re.search(r'(?:未列明|未列入|未收录).{0,50}(?:号|文件|政策)',sentence))
        if absence and not (uncertain or (fragment and not re.search(r'因此|所以|据此|可见|故',sentence))):
            # Only a verbatim explicit exclusion in the supplied text can support this;
            # failure to find an item in a search/excerpt cannot establish its absence.
            if compact(sentence) not in compact(support): issues.append('unverified_document_absence')
        for match in re.finditer(r'(?:全体|所有|全部)[^，。；！？\n]{0,28}(?:老年人|老人|居民|家庭|人员|对象)',sentence):
            if not uncertain and compact(match.group()) not in compact(support):
                issues.append('unsupported_universal_scope')
    return list(dict.fromkeys(issues))
