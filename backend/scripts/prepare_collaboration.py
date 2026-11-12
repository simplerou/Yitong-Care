"""Add only missing collaboration settings; never overwrites existing credentials."""
from pathlib import Path
import re,secrets,argparse
from validation_service.config import ValidationSettings

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--demo',action='store_true',help='显式启用虚构图谱演示模式，禁止真实业务使用');args=p.parse_args()
    path=Path(__file__).resolve().parents[1]/'.env'
    text=path.read_text() if path.exists() else ''
    cfg=ValidationSettings()
    values={'VALIDATION_SERVICE_URL':cfg.validation_service_url,'VALIDATION_SERVICE_TOKEN':cfg.validation_service_token.get_secret_value() or secrets.token_urlsafe(32),'VALIDATION_GRAPH_MODE':cfg.validation_graph_mode,'VALIDATION_ALLOW_DEMO':'true' if cfg.validation_allow_demo else 'false','NEO4J_HTTP_URL':cfg.neo4j_http_url,'NEO4J_DATABASE':cfg.neo4j_database,'NEO4J_USER':cfg.neo4j_user,'NEO4J_PASSWORD':cfg.neo4j_password.get_secret_value()}
    if args.demo:values.update(VALIDATION_GRAPH_MODE='fixture',VALIDATION_ALLOW_DEMO='true')
    for key,value in values.items():
        pattern=rf'(?m)^{key}\s*=.*$'
        exists=re.search(pattern,text)
        if exists:
            if key=='VALIDATION_SERVICE_TOKEN' and not cfg.validation_service_token.get_secret_value():text=re.sub(pattern,f'{key}="{value}"',text)
            elif args.demo and key in ('VALIDATION_GRAPH_MODE','VALIDATION_ALLOW_DEMO'):text=re.sub(pattern,f'{key}="{value}"',text)
        else:text+=f'\n{key}="{value}"'
    path.write_text(text.rstrip()+'\n');path.chmod(0o600)
    print('协作配置已补齐，已有数据库、模型及外部服务密钥未更改；未输出服务令牌。')
    if args.demo:print('已显式启用虚构演示模式；禁止真实诊疗和配餐。')
    elif not cfg.neo4j_password.get_secret_value():print('Neo4j 尚未配置密码，真实图校验在配置前将保持阻断。')
    return 0
if __name__=='__main__':raise SystemExit(main())
