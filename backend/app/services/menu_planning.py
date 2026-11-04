"""Pure planning checks. No disease inference and no identity fields sent to the model."""
from copy import deepcopy
import hashlib
import json
import re
from collections import Counter
from types import SimpleNamespace
from app.services.meals import reasons

def summarize(rows):
    groups={};fingerprint=[];pending=0
    for r in rows:
        p=r['profile'];fingerprint.append((r['id'],r['resident_version'],p['version'] if p else 0,r['reviewed']))
        if not r['reviewed']:pending+=1;continue
        rules={k:p[k] for k in ['allergens','avoid_ingredients','required_tags','allowed_textures']}
        rules={k:sorted(v) for k,v in rules.items()}
        key=json.dumps(rules,sort_keys=True,ensure_ascii=False)
        if key not in groups:groups[key]={'count':0,'requirements':rules}
        groups[key]['count']+=1
    cases=[{'group':f'G{i+1:03d}',**groups[key]} for i,key in enumerate(sorted(groups))]
    digest=hashlib.sha256(json.dumps(sorted(fingerprint)).encode()).hexdigest()
    return {'in_care':len(rows),'reviewed_count':len(rows)-pending,'pending_count':pending,'groups':cases},digest

MEAL_ALIASES={'早餐':'breakfast','午餐':'lunch','晚餐':'dinner'}
TEXTURE_ALIASES={'普通':'normal','普通质地':'normal','软食':'soft','细碎食':'minced','泥糊状食物':'pureed','泥糊状':'pureed'}

def normalize_day(raw,summary):
    """Canonicalize enums, deduplicate ingredient names, and remove unsupported tags. Never add safety data."""
    candidate=deepcopy(raw);changes=[]
    if not isinstance(candidate,dict) or not isinstance(candidate.get('slots'),list):return candidate,changes
    allowed={t for g in summary['groups'] for t in g['requirements']['required_tags']}
    for i,slot in enumerate(candidate['slots']):
        if not isinstance(slot,dict):continue
        if isinstance(slot.get('meal'),str) and slot['meal'].strip() in MEAL_ALIASES:
            slot['meal']=MEAL_ALIASES[slot['meal'].strip()];changes.append({'path':f'slots.{i}.meal','action':'canonical_meal'})
        if not isinstance(slot.get('options'),list):continue
        for j,option in enumerate(slot['options']):
            if not isinstance(option,dict):continue
            path=f'slots.{i}.options.{j}'
            ingredients=option.get('ingredients')
            if isinstance(ingredients,list) and all(isinstance(term,str) for term in ingredients):
                unique=list(dict.fromkeys(term.strip() for term in ingredients))
                if unique!=ingredients:
                    option['ingredients']=unique
                    changes.append({'path':path+'.ingredients','action':'canonical_ingredient_list'})
            if isinstance(option.get('texture'),str) and option['texture'].strip() in TEXTURE_ALIASES:
                option['texture']=TEXTURE_ALIASES[option['texture'].strip()];changes.append({'path':path+'.texture','action':'canonical_texture'})
            if option.get('tags') is None:
                option['tags']=[];changes.append({'path':path+'.tags','action':'empty_unverified_tags'})
            if isinstance(option.get('tags'),list) and all(isinstance(t,str) for t in option['tags']):
                original=option['tags'];kept=list(dict.fromkeys(t.strip() for t in original if t.strip() in allowed))
                if kept!=original:
                    option['tags']=kept;changes.append({'path':path+'.tags','action':'drop_unverified_tags','removed':[t for t in original if t.strip() not in allowed]})
    return candidate,changes

def format_validation_issue(error):
    labels={'name':'方案名称','foods':'具体菜品','ingredients':'食材','allergens':'过敏原','tags':'饮食标签','texture':'食物质地','notes':'制作说明','meal':'餐次类型'}
    loc=list(error['loc']);parts=[];i=0
    while i<len(loc):
        key=loc[i]
        if key in ('slots','options') and i+1<len(loc) and isinstance(loc[i+1],int):
            parts.append(('第'+str(loc[i+1]+1)+'项餐次') if key=='slots' else ('第'+str(loc[i+1]+1)+'套方案'));i+=2;continue
        parts.append(labels.get(key,str(key)) if key!='slots' else '三餐安排');i+=1
    messages={'missing':'缺少必填信息','literal_error':'取值不在允许范围内','extra_forbidden':'包含未约定的字段','list_type':'应填写为列表','string_type':'应填写为文字','too_short':'内容或条目数量不足','too_long':'内容或条目数量过多','model_type':'模型未返回完整的菜单JSON对象'}
    message=messages.get(error['type'],error['msg'].removeprefix('Value error, '))
    return (' / '.join(parts) or '模型回复')+'：'+message

def check_day(day,summary,request):
    hard=[];missing=[]
    allowed=set(request.available_ingredients)
    allowed_tags={tag for case in summary['groups'] for tag in case['requirements']['required_tags']}
    restricted={term for case in summary['groups'] for key in ['allergens','avoid_ingredients'] for term in case['requirements'][key]}
    for slot in day.slots:
        if len(slot.options)!=request.options_per_meal:hard.append(f'{slot.meal}:应提供{request.options_per_meal}套方案，实际为{len(slot.options)}套')
        for index,option in enumerate(slot.options):
            prefix=f'{slot.meal}/方案{index+1}'
            if allowed and not set(option.ingredients)<=allowed:hard.append(prefix+':超出采购清单：'+'、'.join(sorted(set(option.ingredients)-allowed)[:8]))
            if not set(option.tags)<=allowed_tags:hard.append(prefix+':饮食标签只能引用已核实条件中的原词项')
            dish_text=' '.join([option.name,*option.foods])
            omitted=[term for term in restricted if term in dish_text and term not in set(option.ingredients)|set(option.allergens)]
            if omitted:hard.append(prefix+':菜名出现已登记禁忌词项，但食材或过敏原未声明')
            text=' '.join([option.name,*option.foods,option.notes])
            # Remove only explicit negative disclaimers, never a following positive promise.
            claims=re.sub(r'(?:不|不能|无法|不应|不得)(?:保证|承诺|提供|代表)[^，。；\n但却仍]{0,8}(?:疗效|治愈)','',text)
            if re.search(r'治愈|疗效|适合所有|绝对安全|保证.{0,6}(?:降糖|降压|安全)|(?:\d+(?:\.\d+)?)\s*(?:kcal|千卡|千焦|毫克|克|mg)',claims,re.I):hard.append(prefix+':不得输出疗效保证或未核实的精确营养/份量数字')
        for case in summary['groups']:
            profile=SimpleNamespace(data=case['requirements'])
            if not any(not reasons(option.model_dump(),profile) for option in slot.options):missing.append({'group':case['group'],'meal':slot.meal,'count':case['count']})
    return sorted(set(hard)),missing

def food_signature(option):return tuple(sorted(food.strip() for food in option['foods']))
def repetition(slots,previous_slots):
    previous={food_signature(o) for s in previous_slots for o in s['options']}
    current=[food_signature(o) for s in slots for o in s['options']]
    return {'same_as_previous':sum(v in previous for v in current) if previous else 0,'options':len(current),'repeated_within_week':sum(n-1 for n in Counter(current).values() if n>1),'previous_available':bool(previous)}

# Exact dish names only: this is a rotation aid, not a semantic/nutritional assessment.
REPEATABLE_STAPLES={'米饭','白米饭','杂粮饭','糙米饭','馒头','花卷','面条','白粥','小米粥','大米粥'}
def diversity_issues(slots,earlier_slots):
    counts=Counter(food.strip() for slot in earlier_slots for option in slot['options'] for food in option['foods'] if food.strip() not in REPEATABLE_STAPLES)
    issues=[]
    for slot in slots:
        for index,option in enumerate(slot['options']):
            foods=[food.strip() for food in option['foods']]
            minimum=3 if slot['meal']=='breakfast' else 4
            if len(set(foods))<minimum:issues.append(f"{slot['meal']}/方案{index+1}:建议至少{minimum}项不同菜品（含主食），当前{len(set(foods))}项")
            for food in foods:
                if food in REPEATABLE_STAPLES:continue
                counts[food]+=1
                if counts[food]>2:issues.append(f'菜品“{food}”本周出现超过2次，优先更换；特殊饮食必要时可保留并说明')
    return list(dict.fromkeys(issues))
