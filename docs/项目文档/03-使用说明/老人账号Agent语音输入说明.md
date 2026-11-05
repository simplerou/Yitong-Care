# 老人账号 Agent 语音输入说明

更新：2026-11-05。当前已替换浏览器 Web Speech 识别，采用录音 + 后端 Qwen ASR 模型转写。

## 使用方式

老人账号的政策顾问、健康管家、用药管家、膳食营养师、安全守护、心灵陪伴均使用同一输入框：

点击“语音输入” → 允许麦克风 → 说出问题 → 点击“结束录音” → 模型转写 → 核对文字 → 点击发送。

录音时不边说边显示识别文字。完成后可修改药名、数字、年龄和地区，系统不自动发送。原有输入文字保留，识别文字追加在后面；超过1000字时只填入可容纳的部分并明确提示。管理员、工作人员不显示语音入口。

## 模型配置

在本地 `backend/.env` 中已预留：

```dotenv
ASR_API_URL="https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
ASR_MODEL="qwen-audio-3.0-asr-flash"
ASR_API_KEY="填写你的语音服务 API Key"
ASR_TIMEOUT_SECONDS=90
```

ASR 配置与聊天、向量模型完全独立，不会自动复用已有 Key。API Key 只保存在后端，不返回浏览器。

默认地址为阿里云 DashScope 北京地域原生接口。工作空间专属域名、其他地域或 Token Plan 的地址与 Key 必须成对匹配。请填写完整接口 URL，而不是 `/v1` 基础地址；该模型使用 DashScope 音频识别协议，不能直接填 `/chat/completions` 或 `/audio/transcriptions`。第三方平台须确认支持相同的原生请求与返回结构，仅列出同名模型不代表接口兼容。

官方当前也提供工作空间专属地址：`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`，使用时替换实际 WorkspaceId。Token Plan 的模型调用请按其文档使用对应完整地址与专属Key。

填写完成后重启后端、刷新前端。没有 Key 时页面明确提示未配置，不会回退到浏览器自带识别。

## 测试命令

在 backend 目录：

```bash
conda activate agent_env
python -m scripts.check_asr
```

该命令只检查配置格式，不调用模型，不代表权限与连通性已经验证。如需真实转写，准备一份16kHz、单声道、16位PCM的 WAV：

```bash
python -m scripts.check_asr "/path/to/question.wav"
```

也可直接用老人账号在网页录音测试，网页会自动进行格式转换。

## 录音与转写处理

- 浏览器只负责 `getUserMedia` + `MediaRecorder` 录音，不调用 `SpeechRecognition`。
- 支持的录音容器由浏览器选择，录音结束后本地解码、混为单声道并重采样为16kHz PCM WAV。
- 前端以二进制 WAV 向 `/api/speech/transcribe` 提交，后端鉴权限制为老人账号；`/api/speech/config` 只返回是否配置、模型和上限，不返回密钥或服务地址。
- 后端限制文件大小约2.1MB、音频最长65秒（界面60秒自动结束，预留录音收尾），检查真实WAV头、采样率、声道、位宽、帧完整性。
- 后端使用 Base64 Data URI 调用 DashScope 原生非流式音频接口，指定中文识别提示。不提供聊天历史和老人档案，也不执行模型识别出的内容。
- 只有用户点击发送，文字才进入既有Agent问答和会话保存流程。

## 取消与故障

录音阶段可结束，转写阶段可点击“取消转写”。切换会话、账号、Agent、离开页面、页面进入后台或进入提问处理状态时会取消本地录音/转写，并屏蔽迟到结果。等待麦克风权限时取消，即使随后获得流也会释放麦克风。

取消只保证本地不再应用结果；已到服务商的请求可能仍继续处理和计费，不承诺撤销。录音最大60秒，停止回调超时会释放资源。权限拒绝、无设备、音频转换失败、模型超时、鉴权失败与额度问题都有提示，原有文字不清空。

浏览器仍需支持麦克风录音和 Web Audio；使用 HTTPS 或本机 localhost/127.0.0.1。手机访问普通 HTTP 局域网地址仍可能无法使用麦克风，改用模型不能绕过这一浏览器安全要求。

## 音频数据

录音只在点击结束后上传到项目后端，再转发到配置的模型服务商。项目采用原始请求体流式读取，不使用multipart临时文件，不将录音持久保存到数据库、上传目录或日志。模型服务商对音频的处理与保留遵循该服务的条款，项目不作离线或本机识别承诺。请不要说出不必要的身份证号、手机号等隐私信息。

## 验证范围

自动测试验证真实WAV编码、录音/转写状态、取消与迟到结果、权限失败、保留原有文字、鉴权、文件校验、模型请求结构及错误脱敏。模型请求使用模拟HTTP服务，未填真实Key时不进行线上转写。

此前浏览器访问被自动审批拒绝，尚未完成实际麦克风和移动端录音验收；需配置Key后人工验证实际识别效果。

参考接口文档：

- https://help.aliyun.com/en/model-studio/qwen-audio-asr-http-api
- https://help.aliyun.com/zh/model-studio/token-plan-speech-recognition

前端92项测试（含9项录音状态与WAV测试、2项音频接口测试）及生产构建通过；后端音频接口专项9项通过。未进行线上模型调用。
