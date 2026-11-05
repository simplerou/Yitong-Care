"""Explicit local WAV transcription check. No database access or audio persistence."""
import argparse
import asyncio
import sys
from app.services.speech.asr import get_asr,MAX_BYTES
from app.core.exceptions import BusinessError

def main():
    parser=argparse.ArgumentParser(description='检查语音配置；可选传入16kHz单声道PCM16 WAV调用模型转写')
    parser.add_argument('audio',nargs='?',help='本地WAV音频路径')
    args=parser.parse_args();client=get_asr()
    try:
        client.ensure_configured()
        if not args.audio:
            print('ASR 配置已填写（尚未调用服务）：'+client.settings.asr_model)
            print('验证真实识别：python -m scripts.check_asr "/path/to/question.wav"')
            return 0
        with open(args.audio,'rb') as handle:data=handle.read(MAX_BYTES+1)
        result=asyncio.run(client.transcribe(data))
        print('语音模型：'+result['model'])
        print('转写结果：'+result['text'])
        print('未创建会话、未发送给Agent、未保存音频。')
        return 0
    except BusinessError as error:print(error.message);return 1
    except OSError:print('无法读取音频文件，请检查本地文件路径。');return 1

if __name__=='__main__':sys.exit(main())
