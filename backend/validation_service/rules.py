from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from app.operations.contracts import CheckRequest,current_date


def valid_evidence(e):
    try:return bool(e.get('id') and e.get('section') and e.get('location') and e.get('quote') and date.fromisoformat(e['valid_from'])<=current_date() and (not e.get('valid_to') or date.fromisoformat(e['valid_to'])>=current_date()))
    except (KeyError,TypeError,ValueError):return False


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in sorted(value.items())}
    if isinstance(value,list):return sorted((canonical(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True,ensure_ascii=False))
    return value

def evaluate(request:CheckRequest,facts:dict):
    problems=[];paths=[];refs=[];calculations=[]
    def issue(code,**extra):problems.append({'code':code,**extra})
    def evidence(e):
        if not valid_evidence(e):issue('missing_or_expired_evidence');return False
        refs.append(e);return True
    foods=[]
    for food in request.foods:
        fact=facts['foods'].get(food.food_id)
        if not fact:issue('unknown_food',id=food.food_id);continue
        foods.append((food,fact))
    nutrients={key:Decimal('0') for key in ('energy','protein','sodium')}
    nutrition_refs=[]
    for food,fact in foods:
        if fact.get('evidence'):
            if evidence(fact['evidence']):nutrition_refs.append(fact['evidence'])
        elif not facts.get('demo'):issue('missing_nutrition_evidence')
        for key in nutrients:
            try:nutrients[key]+=Decimal(fact[key])*food.grams/100
            except (KeyError,ValueError):issue('unknown_nutrient',id=food.food_id)
    known_allergens={a for f in list(facts['foods'].values())+list(facts['drugs'].values()) for a in f.get('allergens',[])}
    for patient in request.patients:
        if set(patient.diseases)-set(facts.get('diseases',[])):issue('unknown_disease')
        if set(patient.allergens)-known_allergens:issue('unknown_allergen')
        medicines={m.drug_id:m for m in patient.medicines}
        medicines.update({m.drug_id:m for m in request.medicines})
        active={}
        for medicine in medicines.values():
            fact=facts['drugs'].get(medicine.drug_id)
            if not fact:issue('unknown_drug',id=medicine.drug_id);continue
            evidence(fact.get('evidence',{}))
            single=medicine.mg_per_dose;daily=single*medicine.times_daily
            calculations.append({'type':'dose','drug_id':medicine.drug_id,'single':str(single),'daily':str(daily),'unit':'mg'})
            try:
                if single>Decimal(fact['max_single_mg']) or daily>Decimal(fact['max_daily_mg']):issue('dose_limit',id=medicine.drug_id)
            except (KeyError,ValueError):issue('dose_limit_unknown',id=medicine.drug_id)
            if set(fact.get('allergens',[]))&set(patient.allergens):issue('drug_allergen_conflict',id=medicine.drug_id)
            for ingredient in fact['ingredients']:
                if ingredient in active and active[ingredient]!=medicine.drug_id:issue('duplicate_active_ingredient',ingredient=ingredient)
                active[ingredient]=medicine.drug_id
        targets={ingredient:fact['id'] for _,fact in foods for ingredient in fact['ingredients']}
        for conflict in facts['conflicts']:
            a,b=conflict['left'],conflict['right'];med_conflict=a in active and b in active
            food_conflict=(a in active and b in targets) or (b in active and a in targets)
            if med_conflict or food_conflict:
                evidence(conflict['evidence']);issue('polypharmacy' if med_conflict else 'food_drug_conflict',rule=conflict['rule'])
                left=a if a in active else b;right=b if left==a else a
                paths.append({'rule':conflict['rule'],'nodes':[active[left],left,right,active.get(right,targets.get(right))], 'evidence':conflict['evidence']})
        for _,fact in foods:
            overlap=set(fact['allergens'])&set(patient.allergens)
            if overlap:issue('allergen_conflict',food_id=fact['id'],allergens=sorted(overlap))
        for conflict in facts.get('disease_conflicts',[]):
            if conflict['disease'] in patient.diseases and conflict['ingredient'] in set(active)|set(targets):
                evidence(conflict['evidence']);issue('disease_contraindication',rule=conflict['rule'])
                paths.append({'rule':conflict['rule'],'nodes':[conflict['disease'],conflict['ingredient']],'evidence':conflict['evidence']})
        if request.kind in ('menu','meal_swap'):
            if not request.foods:issue('foods_required')
            if not patient.energy_min<=nutrients['energy']<=patient.energy_max:issue('energy_target')
            if nutrients['protein']<patient.protein_min:issue('protein_target')
            if nutrients['sodium']>patient.sodium_max:issue('sodium_limit')
    if request.kind=='medication' and not request.medicines:issue('medicines_required')
    total=Decimal('0');priced=True
    items=request.medicines if request.kind=='medication' else request.foods
    for item in items:
        fact=facts['drugs' if request.kind=='medication' else 'foods'].get(item.drug_id if request.kind=='medication' else item.food_id,{})
        price=fact.get('cost_per_mg_cny' if request.kind=='medication' else 'cost_per_100g_cny')
        if price is None:priced=False;continue
        quantity=item.mg_per_dose*item.times_daily if request.kind=='medication' else item.grams/100
        total+=Decimal(price)*quantity
    cost={'complete':priced and bool(items),'amount_cny':str(total.quantize(Decimal('.01'))) if priced and items else None,'basis':'已登记单价的一日估算；不含服务费用，缺失单价不按0处理'}
    return {'cost':cost,'passed':not problems,'rule_version':facts['version'],'graph_hash':sha256(json.dumps(canonical(facts),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'demo':bool(facts.get('demo')),'issues':problems,'paths':paths,'references':list({e['id']:e for e in refs}.values()),'nutrition_references':nutrition_refs,'calculations':calculations,'nutrients':{k:str(v) for k,v in nutrients.items()},'risk':3 if request.kind=='medication' else 2}
