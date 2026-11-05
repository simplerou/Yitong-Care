from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.auth import require_account
from app.core.exceptions import BusinessError
from app.services.speech.asr import ASRClient,get_asr,MAX_BYTES

router=APIRouter(prefix='/speech',tags=['speech'])
def resident(account=Depends(require_account)):
    if account.role!='resident':raise HTTPException(403,'语音提问目前仅供老人账号使用')
    return account

@router.get('/config',dependencies=[Depends(resident)])
def config(response:Response,client:Annotated[ASRClient,Depends(get_asr)]):
    response.headers['Cache-Control']='no-store'
    return client.configuration()

@router.post('/transcribe',dependencies=[Depends(resident)])
async def transcribe(request:Request,response:Response,client:Annotated[ASRClient,Depends(get_asr)]):
    client.ensure_configured()
    if request.headers.get('content-type','').split(';')[0].strip().lower()!='audio/wav':raise BusinessError('请提交 WAV 格式录音。',415)
    # Raw streaming body avoids multipart temporary files and rejects oversize uploads early.
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>MAX_BYTES:raise BusinessError('录音文件过大，请缩短录音。',413)
        data.extend(chunk)
    response.headers['Cache-Control']='no-store'
    return await client.transcribe(bytes(data))
