"""Fixed, read-only business-skill loading. No user-selected paths or executable resources."""
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
import re
from app.core.exceptions import BusinessError

NAME='eldercare-policy'
RESOURCES=('SKILL.md','references/query-analysis.md','references/evidence-answer.md')

@dataclass(frozen=True)
class PolicySkill:
    name:str
    version:str
    sha256:str
    instructions:str
    understanding:str
    answering:str

    def metadata(self):return {'name':self.name,'version':self.version,'sha256':self.sha256}
    def prompt(self,stage,contract):
        if stage not in {'understand','generate'}:raise ValueError('unsupported policy skill stage')
        reference=self.understanding if stage=='understand' else self.answering
        # Code-owned security and output contracts follow business guidance.
        return self.instructions+'\n\n'+reference+'\n\n【程序输出契约】\n'+contract


def load_policy_skill(root=None):
    """No global prompt cache: the next request observes a resource update.

    root is an internal test seam, never populated from API input or model output.
    """
    root=root if root is not None else files('app.skills').joinpath(NAME)
    try:
        texts=[]
        for name in RESOURCES:
            text=root.joinpath(name).read_text(encoding='utf-8')
            if not text.strip() or len(text)>50_000:raise ValueError('invalid skill resource size')
            texts.append(text)
        front=re.fullmatch(r'---\s*\n(.*?)\n---\s*\n(.+)',texts[0],re.S)
        if not front:raise ValueError('missing frontmatter')
        metadata,instructions=front.groups()
        if not re.search(r'^name: eldercare-policy\s*$',metadata,re.M):raise ValueError('unexpected skill name')
        if not re.search(r'^description: .+\S',metadata,re.M):raise ValueError('missing description')
        version=re.search(r'^  version: "(\d+\.\d+\.\d+)"\s*$',metadata,re.M)
        if not version:raise ValueError('missing skill version')
        digest=sha256()
        for path,text in zip(RESOURCES,texts):digest.update(path.encode()+b'\0'+text.encode()+b'\0')
        return PolicySkill(NAME,version.group(1),digest.hexdigest(),instructions.strip(),texts[1].strip(),texts[2].strip())
    except (OSError,ValueError,UnicodeError):
        raise BusinessError('政策顾问 Skill 规则加载失败，请检查项目中的业务规则文件。',503) from None
