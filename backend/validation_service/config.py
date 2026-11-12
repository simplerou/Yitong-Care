from pathlib import Path
from pydantic import SecretStr,Field
from pydantic_settings import BaseSettings,SettingsConfigDict
class ValidationSettings(BaseSettings):
    model_config=SettingsConfigDict(env_file=Path(__file__).resolve().parents[1]/'.env',extra='ignore')
    validation_service_token:SecretStr=SecretStr('')
    validation_service_url:str='http://127.0.0.1:8100'
    validation_graph_mode:str='neo4j'
    validation_allow_demo:bool=False
    neo4j_http_url:str='http://127.0.0.1:7474'
    neo4j_database:str=Field(default='neo4j',pattern=r'^[a-zA-Z0-9_-]+$')
    neo4j_user:str='neo4j'
    neo4j_password:SecretStr=SecretStr('')
