from shutil import copytree
import pytest
from app.core.exceptions import BusinessError
from app.services.policy_skill import load_policy_skill
from app.services.chat.prompt_builder import build_policy_prompts
from importlib.resources import files

@pytest.fixture
def root(tmp_path):
    source=files('app.skills').joinpath('eldercare-policy')
    copytree(str(source),tmp_path/'eldercare-policy')
    return tmp_path/'eldercare-policy'


def test_stage_specific_loading_and_next_request_refresh(root,monkeypatch):
    analysis=root/'references/query-analysis.md';answer=root/'references/evidence-answer.md'
    analysis.write_text(analysis.read_text()+'\nANALYSIS_ONLY\n')
    answer.write_text(answer.read_text()+'\nANSWER_ONLY\n')
    monkeypatch.setattr('app.services.chat.prompt_builder.load_policy_skill',lambda:load_policy_skill(root))
    skill,u,g=build_policy_prompts()
    assert 'ANALYSIS_ONLY' in u and 'ANALYSIS_ONLY' not in g
    assert 'ANSWER_ONLY' in g and 'ANSWER_ONLY' not in u
    assert u.endswith('不要输出其他字段。')
    answer.write_text(answer.read_text()+'\nNEXT_REQUEST_RULE\n')
    newer,u2,g2=build_policy_prompts()
    assert 'NEXT_REQUEST_RULE' not in g and 'NEXT_REQUEST_RULE' in g2
    assert skill.sha256!=newer.sha256
    assert skill.version==newer.version=='1.0.0'


@pytest.mark.parametrize('failure',['missing','empty','bad_version'])
def test_invalid_skill_fails_closed(root,failure):
    if failure=='missing':(root/'references/evidence-answer.md').unlink()
    elif failure=='empty':(root/'references/query-analysis.md').write_text('')
    else:
        p=root/'SKILL.md';p.write_text(p.read_text().replace('"1.0.0"','"broken"'))
    with pytest.raises(BusinessError) as error:load_policy_skill(root)
    assert error.value.status_code==503


def test_skill_does_not_allow_dynamic_stage_paths():
    with pytest.raises(ValueError):load_policy_skill().prompt('../../private','contract')
