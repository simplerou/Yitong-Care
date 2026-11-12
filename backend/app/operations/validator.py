import httpx
from fastapi import HTTPException
from validation_service.config import ValidationSettings

class ValidationClient:
    def __init__(self,settings=None,transport=None):self.settings=settings or ValidationSettings();self.transport=transport
    def request(self,path,payload=None):
        token=self.settings.validation_service_token.get_secret_value()
        if not token:raise HTTPException(503,'请配置独立校验服务；不可用时禁止生成草稿')
        try:
            from app.operations.budget import remaining
            with httpx.Client(timeout=remaining(),transport=self.transport,follow_redirects=False) as client:
                response=client.request('POST' if payload is not None else 'GET',self.settings.validation_service_url.rstrip('/')+path,headers={'Authorization':'Bearer '+token},json=payload)
                if response.status_code!=200:raise HTTPException(503,'独立校验服务或有效证据不可用，禁止生成草稿')
                result=response.json()
                if not isinstance(result,dict):raise ValueError()
                return result
        except (httpx.HTTPError,ValueError):raise HTTPException(503,'独立校验服务不可用，禁止生成草稿') from None
    def check(self,payload):
        result=self.request('/check',payload)
        from app.operations.contracts import ValidationResult
        from pydantic import ValidationError
        try:return ValidationResult.model_validate(result).model_dump(mode='json')
        except ValidationError:raise HTTPException(503,'校验服务响应不符合安全契约，禁止生成草稿') from None
    def catalog(self):return self.request('/catalog')
    def evidence(self,drug):
        from urllib.parse import quote
        return self.request('/evidence/'+quote(drug,safe=''))
def get_validator():return ValidationClient()
