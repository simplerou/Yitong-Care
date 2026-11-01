"""Small user-only consultation state. Does not extract facts from assistant answers."""
import re
import jieba
from app.schemas.policy import DialogueState

BENEFITS = {
    '高龄老年人养老服务补贴':'养老服务补贴',
    '养老服务补贴':'养老服务补贴',
    '高龄老人生活津贴':'高龄津贴',
    '高龄津贴':'高龄津贴', '高龄补贴':'高龄津贴',
    '养老长期护理保险':'长期护理保险', '长期护理保险':'长期护理保险', '长护险':'长期护理保险',
    '养老护理补贴':'养老护理补贴', '失能护理补贴':'养老护理补贴',
    '适老化改造补贴':'适老化改造补贴', '助餐补贴':'助餐补贴',
    '基本生活补助':'基本生活补助',
}
ASPECTS = {'服务项目':'服务项目','服务内容':'服务项目','支付范围':'支付范围',
           '待遇标准':'待遇标准','支付比例':'支付比例','报销比例':'支付比例','参保条件':'参保条件',
           '参保对象':'参保条件','申请条件':'申请条件','申请流程':'办理流程','怎么办理':'办理流程',
           '失能评估':'失能评估流程','办理流程':'办理流程'}


def locations(text):
    tokens=list(jieba.cut(text,HMM=False))
    cities=[t for t in tokens if len(t)>2 and t.endswith(('市','省'))]
    districts=[t for t in tokens if len(t)>2 and t.endswith(('区','县')) and not t.endswith('自治区')]
    return cities,districts


def advance_dialogue(state, text):
    state=state.model_copy(deep=True)
    if re.search(r'换个人|另一个人|帮朋友|我父亲|我母亲|我爸爸|我妈妈|重新开始|换个话题',text):
        state=DialogueState()
    uncertain=bool(re.search(r'不确定|不知道|不清楚|可能',text))
    positive_text=re.sub(r'(?:不是|并非)\s*\d{1,3}\s*(?:周岁|岁)','',text)
    ages=re.findall(r'(?<!\d)(\d{1,3})\s*(?:周岁|岁)',positive_text)
    if ages and len(set(ages))==1:
        if uncertain: state.age=None
        elif 0<=int(ages[0])<=130: state.age=int(ages[0])
    elif re.search(r'(?:不是|并非)\s*\d{1,3}\s*(?:周岁|岁)',text): state.age=None
    if re.search(r'(?:年龄|岁数).{0,5}(?:不确定|不知道|不清楚)|不(?:确定|知道|清楚).{0,5}(?:年龄|岁数)',text): state.age=None
    # Explicit domicile before 户籍/户口 wins over places mentioned for comparison.
    household_match=re.search(r'[^，。；?？\n]{0,40}(?:户籍|户口)',text)
    household_after=re.search(r'(?:户籍|户口)(?:在|为|是|[:：])([^，。；?？\n]{1,30})',text)
    personal_locations=(household_match.group(0) if household_match else '') + (household_after[1] if household_after else '') if household_match else text
    if not household_match and re.search(r'[?？]|吗|能否|是否|根据.*号',text): personal_locations=''
    cities,districts=locations(personal_locations)
    # A comma-separated district answer is still an explicit location reply.
    if not re.search(r'[?？]|吗|能否|是否|根据.*号|对比|比较|套用|参照|文件',text):
        _,districts=locations(text)
    if cities:
        if state.region and state.region!=cities[-1]:
            state.district='';state.household=''
        state.region=cities[-1]
    if districts: state.district=districts[-1]
    if household_match and not uncertain:
        home_cities,home_districts=locations(personal_locations)
        if home_cities or home_districts:
            state.household=''.join(home_cities[-1:]+home_districts[-1:])+'户籍'
    if re.search(r'(?:户籍|户口).{0,5}(?:不确定|不知道|不清楚)',text): state.household=''
    choices=[]
    for alias,benefit in BENEFITS.items():
        for match in re.finditer(re.escape(alias),text):
            prefix=text[max(0,match.start()-4):match.start()]
            if re.search(r'不问|不是|不咨询',prefix): continue
            choices.append((match.start(),len(alias),benefit))
    if choices:
        # Prefer the longest category at the same ending position (e.g. 高龄老年人养老服务补贴).
        _,_,benefit=max(choices,key=lambda item:(item[0]+item[1],item[1]))
        if state.benefit!=benefit: state.aspect=''
        state.benefit=benefit
    aspects=[(text.rfind(word),aspect) for word,aspect in ASPECTS.items() if word in text]
    if aspects: state.aspect=max(aspects,key=lambda pair:pair[0])[1]
    elif not state.aspect and re.search(r'能申请|能领|领取|申请补贴',text): state.aspect='申请条件'
    return state


def build_dialogue(texts, base=None):
    state=base or DialogueState()
    for text in texts: state=advance_dialogue(state,text)
    return state


def context_query(state, question):
    """Only resolve short slot/aspect replies; preserve full explicit questions verbatim."""
    if len(question)>60 or re.search(r'[?？]|吗|能否|是否|根据.*号|是不是|多少钱|多少元',question): return question
    if not (state.region and state.benefit): return question
    remainder=question
    for word in sorted([*BENEFITS,*ASPECTS],key=len,reverse=True): remainder=remainder.replace(word,'')
    cities,districts=locations(question)
    for word in cities+districts: remainder=remainder.replace(word,'')
    remainder=re.sub(r'\d{1,3}\s*(?:周岁|岁)','',remainder)
    remainder=re.sub(r'户籍|户口|我想了解|想了解|我今年|今年|我是|我|的|是|为|呢|[\s，,。；;：:]','',remainder)
    if remainder: return question
    subject=state.region+state.district+'的'+state.benefit
    question=subject+'：'+(state.aspect or '申请条件及政策说明')+'。'
    facts=[]
    if state.age is not None: facts.append(f'用户提供的年龄为{state.age}岁')
    if state.household: facts.append('用户提供的户籍为'+state.household)
    return question+('已知用户条件：'+'；'.join(facts)+'。' if facts else '')
