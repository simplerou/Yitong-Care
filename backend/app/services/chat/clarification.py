"""Bounded routing guards; a confirmed personal condition never proves policy eligibility."""
import re

AFFIRMATIVE = re.compile(r'^(?:是的?|对的?|没错|是这样|确认|嗯|是这个地区)[。！!，,\s]*$')


def explicit_standard_question(text):
    """A named-file standard explanation already giving domicile and age can retrieve first."""
    standard_intent = bool(re.search(r'标准|多少|金额', text))
    amount_check = bool(re.search(r'是不是|是否|对吗|正确吗|属实|核实', text)
                        and re.search(r'\d+(?:\.\d+)?\s*元', text)
                        and re.search(r'补贴|津贴|补助|待遇', text))
    return bool(re.search(r'[〔\[]20\d{2}[〕\]]\s*\d+号', text)
                and re.search(r'[市区县]户籍', text)
                and re.search(r'\d{1,3}\s*(?:周岁|岁)', text)
                and (standard_intent or amount_check)
                and not re.search(r'我能|能否申请|是否符合|申请资格|能不能领', text))


def confirmed_question(question, history):
    if not AFFIRMATIVE.fullmatch(question.strip()) or len(history)<2:
        return None
    previous=history[-1]
    if previous.role!='assistant': return None
    clarification=previous.content.strip()
    # Only a single, positive binary question about personal conditions is eligible.
    if not re.search(r'是否|是不是|是.{1,30}吗', clarification): return None
    if not re.search(r'户籍|年龄|周岁|所在|地区|低保|失能', clarification): return None
    if re.search(r'资格|有效|金额|标准|不|以及|或者|还是|、', clarification): return None
    if len(re.findall(r'[？?]',clarification))>1: return None
    original=next((turn.content for turn in reversed(history[:-1])
                   if turn.role=='user' and not AFFIRMATIVE.fullmatch(turn.content.strip())),None)
    if not original: return None
    resolved=original+'\n用户针对上一轮条件追问作出肯定确认：'+clarification+' 回答：'+question
    return resolved if len(resolved)<=1000 else None


def same_clarification(left, right):
    return re.sub(r'[\s？?。！!，,]','',left)==re.sub(r'[\s？?。！!，,]','',right)


AGE_FOLLOWUP = re.compile(r'^(?:(?:那如果|那么|如果|那|改成|换成|应该是|是|我刚才说错了[，,]?是)\s*)?(\d{1,3})\s*(?:周岁|岁)(?:的老人)?(?:呢|的话|怎么样|是多少)?[？?。！!\s]*$')


def age_followup_question(question, history):
    """Replace only an age in the nearest user-specified, complete standard question.

    Never borrow a location/category from assistant prose or jump across a new topic.
    """
    match=AGE_FOLLOWUP.fullmatch(question.strip())
    if not match or not 0<=int(match[1])<=130: return None
    for turn in reversed(history):
        if turn.role!='user': continue
        if AGE_FOLLOWUP.fullmatch(turn.content.strip()) or AFFIRMATIVE.fullmatch(turn.content.strip()): continue
        if not explicit_standard_question(turn.content): return None
        age_mentions=list(re.finditer(r'\d{1,3}\s*(?:周岁|岁)',turn.content))
        if len(age_mentions)!=1: return None
        mention=age_mentions[0]
        resolved=turn.content[:mention.start()]+match[1]+'岁'+turn.content[mention.end():]
        return resolved if len(resolved)<=1000 else None
    return None


def explicit_applicability_question(text):
    """A document-scope question can retrieve without collecting personal eligibility data."""
    return bool(re.search(r'[〔\[]20\d{2}[〕\]]\s*\d+号',text)
                and re.search(r'[市区县]户籍',text)
                and re.search(r'标准|补贴|津贴|待遇',text)
                and re.search(r'(?:可以|能否|能不能|是否|可否).{0,8}(?:按|套用|参照|适用)|直接(?:按|套用|参照|适用)',text))


FIELD_PATTERNS = {
    'age': r'年龄|岁数|几岁|多少岁',
    'household_region': r'户籍|户口',
    'district': r'哪个区|哪个县|区县|所在(?:的)?区|具体.{0,4}区',
    'residence': r'居住地|常住地|住在哪|现住',
    'benefit': r'(?:补贴|津贴|保障|待遇|保险)(?:的)?(?:类型|类别|种类)|哪(?:一)?类|哪种(?:补贴|保险)',
    'income': r'收入|经济状况|是否.{0,5}(?:低保|低边)|(?:低保|低边)(?:资格|情况)',
    'disability': r'失能等级|失能评估|自理能力',
}
FIELD_QUESTIONS = {
    'age': '咨询对象的年龄',
    'household_region': '咨询对象的户籍地区',
    'district': '所在区或县',
    'residence': '咨询对象的现居住地',
    'benefit': '想了解的补贴或保障类别（例如养老服务补贴、失能护理补贴或长期护理保险）',
    'income': '咨询对象的收入或低保、低边情况',
    'disability': '咨询对象是否已有失能评估及其等级',
}


def explicitly_provided_fields(question, history):
    """Bounded user-only field presence. Never infer eligibility or copy assistant examples."""
    texts=[turn.content for turn in history if turn.role=='user']+[question]
    # A new person may have different conditions: do not transfer prior personal details.
    if re.search(r'换个人|另一个人|帮朋友|我父亲|我母亲|我爸爸|我妈妈',question): texts=[question]
    known=set()
    for text in texts:
        uncertain=bool(re.search(r'不确定|不知道|不清楚|可能|(?<!是)不是',text))
        age_values=re.findall(r'(?<!\d)(\d{1,3})\s*(?:周岁|岁)',text)
        if age_values:
            known.discard('age')
            if not uncertain and len(set(age_values))==1 and 0<=int(age_values[0])<=130: known.add('age')
        if re.search(r'[市区县](?:的)?(?:户籍|户口)|(?:户籍|户口)(?:在|为|是|[:：])[^，。；\n]{1,20}[市区县]',text):
            known.discard('household_region')
            if not uncertain: known.add('household_region')
        district=bool(re.search(r'[区县](?:的)?(?:户籍|户口)|(?:户籍|户口)(?:在|为|是|[:：])[^，。；\n]{1,20}[区县]',text) or re.fullmatch(r'[\u4e00-\u9fff]{2,8}[区县](?:的|户籍|户口)?[。\s]*',text.strip()))
        if district and not uncertain and not re.search(r'哪个|什么|哪里',text): known.add('district')
        if re.search(r'养老服务补贴|养老护理补贴|失能护理补贴|长期护理保险|长护险|高龄津贴|高龄老人生活津贴|适老化改造补贴|助餐补贴|基本生活补助',text):
            if not uncertain: known.add('benefit')
        if re.search(r'(?:年龄|岁数|户籍|户口).{0,5}(?:不确定|不知道|不清楚)',text):
            if re.search(r'年龄|岁数',text): known.discard('age')
            if re.search(r'户籍|户口',text): known.discard('household_region')
    return known


def remaining_clarification(clarification, known, missing_fields=()):
    inferred=[field for field,pattern in FIELD_PATTERNS.items() if re.search(pattern,clarification)]
    requested=list(dict.fromkeys([*missing_fields,*inferred]))
    # No evidence of a repeated known field: retain the original, including open questions.
    if not set(requested).intersection(known): return clarification
    remaining=[field for field in requested if field not in known]
    if not remaining: return None
    return '请补充'+ '、'.join(FIELD_QUESTIONS[field] for field in remaining)+'。'
