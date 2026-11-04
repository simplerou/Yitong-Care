from app.services.diet_profile_reader import extract
class Reader:
    model='fake'
    def __init__(self,facts):self.facts=facts
    def complete_json(self,*args,**kwargs):return {'facts':self.facts,'questions':[]}
def test_evidence_and_unconfirmed():
    result=extract({'allergies':'鸡蛋过敏','dietary_notes':'需软食'},Reader([
        dict(field='allergens',value='鸡蛋',source='allergies',quote='鸡蛋过敏'),
        dict(field='allowed_textures',value='软食',source='dietary_notes',quote='需软食'),
        dict(field='avoid_ingredients',value='糖',source='dietary_notes',quote='禁止糖')]))
    assert result['suggestion']['allergens']==['鸡蛋']
    assert result['suggestion']['allowed_textures']==['soft']
    assert result['suggestion']['avoid_ingredients']==[]
    assert result['suggestion']['confirmed'] is False
    assert result['saved'] is False and result['rejected_count']==1
def test_unknown_stays_unknown():
    result=extract({'allergies':'未记录','dietary_notes':''},Reader([]))
    assert result['suggestion']['allergy_status']=='unknown'
    assert result['suggestion']['allowed_textures']==[]
