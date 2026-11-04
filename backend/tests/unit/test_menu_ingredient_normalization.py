from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.schemas.meals import PlannedDay
from app.services.menu_planning import normalize_day


def test_duplicate_ingredients_are_preserved_once_without_mutating_model_output():
    raw={'slots':[{'options':[{'ingredients':['鱼肉糜','鸡蛋','紫菜','鸡蛋',' 盐 ']}]}]}
    before=deepcopy(raw)
    result,changes=normalize_day(raw,{'groups':[]})
    assert result['slots'][0]['options'][0]['ingredients']==['鱼肉糜','鸡蛋','紫菜','盐']
    assert raw==before
    assert changes[0]['path']=='slots.0.options.0.ingredients'


@pytest.mark.parametrize('bad',['','x'*61])
def test_invalid_ingredients_are_not_silently_removed(bad):
    option={'name':'餐食','foods':['蒸蛋'],'ingredients':['鸡蛋',bad],'allergens':['鸡蛋'],'tags':[],'texture':'normal','notes':''}
    raw={'slots':[{'meal':meal,'options':[deepcopy(option)]} for meal in ['breakfast','lunch','dinner']]}
    normalized,_=normalize_day(raw,{'groups':[]})
    with pytest.raises(ValidationError):
        PlannedDay.model_validate(normalized)
