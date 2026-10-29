# 颐养通后端

当前提供 MySQL 数据层、文档上传与真实解析、文档管理、后端切块预览与保存，以及健康检查。目标数据库为 MySQL 8.0，字符集 utf8mb4，存储引擎 InnoDB。

## 1. 安装依赖

使用你已有的 `agent_env`，在 `Yitong Care/backend` 目录执行：

```sh
conda activate agent_env
python -m pip install -e '.[dev]'
```

其他开发机需要 Python 3.11 或更新版本，也可以独立创建虚拟环境：

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

若本机使用 Python 3.12，把第一行解释器换成 `python3.12`。

当前开发机已准备 Python 3.11 的 `.venv`，为离线开发复用了本机 Conda `agent_env` 中已有的依赖；可直接激活使用。换机或重新创建环境时按上面的安装步骤执行。

## 2. 填写连接信息

首次使用时将 `.env.example` 复制成 `.env`（已有 `.env` 时保留现有配置），填写 MySQL 地址、数据库、用户名、密码。配置从后端目录的 `.env` 读取，与终端当前目录无关；同名系统环境变量优先。

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=yitong_care
MYSQL_USER=yitong
MYSQL_PASSWORD="填写实际密码"
```

含空格或 `#` 的密码请保留引号。密码中的 `@`、`:`、`/` 等字符直接填写，无需 URL 编码。

本地 MySQL 使用 Unix socket 时设置 `MYSQL_UNIX_SOCKET=/tmp/mysql.sock`；远程或 TCP 连接保持该字段为空。

`.env` 已被 Git 忽略，`.env.example` 可以提交。应用不会自动建库或建表。

## 3. 建库与迁移

推荐由管理员预先创建数据库，并为项目配置独立账号。账号应至少具备该数据库的读写权限；执行迁移还需要 CREATE / ALTER / INDEX / REFERENCES 等 DDL 权限。

若当前配置的账号具备建库权限，可以执行：

```sh
python -m scripts.create_database
```

该命令只创建不存在的数据库，不更改已有数据库的结构或字符集。已有数据库应确认字符集为 utf8mb4。

执行只读连接检查，再应用迁移：

```sh
python -m scripts.check_db
alembic upgrade head
alembic current
```

第一版迁移创建 4 张业务表及 Alembic 的版本表：

| 表 | 用途 |
| --- | --- |
| knowledge_base | 知识库分类 |
| knowledge_document | 文档元信息、解析正文和状态 |
| document_chunk | 片段、原文位置、Embedding 字节及模型维度 |
| vector_index | FAISS 派生索引的版本与状态 |

`document_chunk.id` 使用 BIGINT，与 FAISS 的 int64 ID 对齐；Embedding 保存为 float32 小端字节的 MEDIUMBLOB，具体序列化由后续向量服务完成。正文建立 `FULLTEXT ... WITH PARSER ngram` 索引，目标 MySQL 实例需支持内置 ngram 解析器。

时间使用 UTC 会话，DATETIME 字段保存 UTC；`updated_at` 由 ORM 更新时维护。FAISS 仍是后续阶段的派生索引，不在此次接入中运行。

## 4. 启动 API

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- `GET /api/health`：应用存活检查，不访问数据库。
- `GET /api/health/db`：执行 SELECT 1；连接正常返回 200，失败返回 503。此接口只检查连通性，不代表建表迁移已完成。
- `GET /docs`：OpenAPI 文档。

连接池使用失效连接检测、30 分钟回收和连接超时，不把密码或底层连接错误返回给客户端。会话异常时回滚；业务写入需在服务层显式提交事务。

## 5. 检查

```sh
pytest
alembic upgrade head --sql
```

单元测试和接口测试不依赖正在运行的 MySQL。`--sql` 只输出迁移 SQL，不修改数据库；真实数据库应在连接信息填写后通过 `check_db` 和在线迁移验证。

## 6. 文档与切块接口

启动前执行 `alembic upgrade head`。迁移版本 `20261028_0002` 增加“通用知识库”，上传默认使用 `kb_id=general`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/knowledge-bases` | 可选知识库 |
| POST | `/api/documents` | multipart：file、kb_id、source；返回 202 和解析中文档 |
| GET | `/api/documents` | q 名称搜索、page/page_size 分页，含数据库统计 |
| GET | `/api/documents/{id}` | 元数据、真实解析正文和全部已保存文本块 |
| POST | `/api/documents/{id}/parse:retry` | 解析失败或超过 10 分钟后重试 |
| DELETE | `/api/documents/{id}` | 删除文档和文本块，失效相关索引，清理原文件 |
| POST | `/api/documents/{id}/chunks:preview` | size/overlap 参数预览，不写数据库 |
| POST | `/api/documents/{id}/chunks` | 保存切块，新块 embedding 为空，旧向量失效 |
| GET | `/api/chunks/{id}` | 文本块原文和字符位置 |

支持 TXT / Markdown（UTF-8、UTF-16 BOM、GB18030）、文字 PDF、DOCX 主文档段落及表格。DOCX 通过 ZIP + 安全 XML 解析提取 WordprocessingML 正文；旧版 DOC、加密文件与扫描件 OCR 暂不支持，会明确提示。文档上限 50MB、解析正文上限 200 万字符，PDF 上限 1000 页。拒绝非法扩展名、空文件和过大的解压内容。

原文件使用随机文件名写入 `backend/var/uploads`，由本地存储适配器管理，Git 已忽略。通过 `UPLOAD_DIR` 可指定绝对路径。MySQL 保存元数据、解析正文和文本块；这一阶段没有依赖 MinIO。不要把上传目录当成可随意删除的缓存。

解析任务目前使用 FastAPI 进程内后台任务和独立数据库会话；生产阶段再迁入 Redis/Worker。解析中文档不能删除或切块。服务重启导致中断时，超过 10 分钟的解析任务可通过页面“重试”恢复；多个 API 实例尚不支持任务去重。

字符位置按解析正文的 Unicode 字符计数，`content[start_offset:start_offset+chars]` 与片段一致。预览会回传实际重叠字数；超长句按字符截断。保存新切块是事务操作，会删除旧块、清空旧向量并把相关 `vector_index` 标记为 stale。

当前数据库集成接口测试使用隔离的 SQLite 测试库及测试专用类型映射验证事务和级联行为；MySQL 方言 DDL 另行编译检查。这不替代真实 MySQL 上的在线迁移与联调。

前端知识库、切块、向量入库、混合检索和检索记录已连接真实接口。Agent 问答仍为独立演示，后续将复用后端检索能力。


## 7. 向量入库、FAISS 与混合检索

先在 `agent_env` 安装新增依赖并应用最新迁移：

```sh
python -m pip install -e '.[dev]'
alembic upgrade head
alembic current
```

最新版本为 `20261028_0003`，增加 `embedding_task`、`retrieval_log`、`retrieval_hit` 三张表，以及索引文件校验和字段。已有文档和文本块保留。

模型配置读取 `.env` 中的 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS`、`EMBEDDING_TIMEOUT_SECONDS`。当前用户配置为 `qwen3.7-text-embedding` / 1024 维；聊天模型配置暂不参与这一阶段。修改配置后重启后端。可用 `python -m scripts.check_models` 单独测试模型。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/embeddings/models` | 当前配置模型、维度和可用状态，不返回密钥 |
| POST | `/api/documents/{id}/embeddings` | 创建入库任务，body 为 model（可选）与 batch_size（8/16/32） |
| GET | `/api/embeddings/tasks` | 最近任务，可按 doc_id 筛选，刷新页面可恢复进度 |
| GET | `/api/embeddings/tasks/{id}` | 阶段、进度、批次日志与错误 |
| POST | `/api/embeddings/tasks/{id}/retry` | 失败重试或恢复中断任务，跳过已完成批次 |
| GET | `/api/vector-index/status` | 当前模型索引版本、数量、文件校验及数据库对账 |
| POST | `/api/vector-index/rebuild` | 从 MySQL 重建当前模型索引，body 为 `{}` 或 kb_id |
| POST | `/api/retrieval/search` | query、scope（all 或文档 ID）、top_k（3/5/10）、threshold（0.02–0.6） |
| GET | `/api/retrieval/logs` | 数据库中的检索记录，page/page_size 分页 |
| GET | `/api/retrieval/logs/{id}` | 回放历史结果快照 |
| DELETE | `/api/retrieval/logs/{id}` | 删除一条检索记录和其快照 |
| DELETE | `/api/retrieval/logs` | 清空检索记录和快照 |

Embedding 适配器调用 OpenAI 兼容的 `/embeddings` 接口，每次最多发送 10 条，以兼容不同通义模型；用户选择的批次仍以 8/16/32 为处理进度单位。响应按 index 重排，校验条数、维度、有限数值和非零范数，归一化后以 float32 小端 BLOB 保存至 MySQL。

服务地址、模型名、维度和 `EMBEDDING_REVISION` 共同生成模型标识，禁止不同标识的向量混入同一索引。更换同名模型的实际权重时递增 `EMBEDDING_REVISION`，并重新入库。

索引使用真实 `faiss.IndexIDMap2(IndexFlatIP)`，以文本块 BIGINT ID 建立映射。发布时写临时文件、fsync、原子重命名，再提交数据库版本记录；文件不可变，读侧按版本和文件状态热加载，验证 SHA-256、维度和条数。数据库提交失败时旧版本仍然有效；未被数据库引用的新文件不参与检索。旧版本文件暂时保留，后续再加入自动清理策略。

当前以 macOS/Linux 单机文件锁实现跨进程单写者：一个时间只执行一个入库任务；切块保存、文档删除与索引重建也使用相同写锁。已有索引的读取不占写锁。入库期间当前文档暂不参与检索，其余已入库文档可继续读取旧索引。后台任务仍运行在 API 进程内；服务中断后点击“恢复中断任务”。任务和批次结果保存在 MySQL，重试不重发成功批次。尚未使用 Redis 任务队列，也不支持多机共享写入。

页面加载索引概览时会进行数量和 ID 对账；检索时检查版本、文件完整性和允许访问的块 ID。文件丢失、损坏或索引缺少当前向量会提示重建。也可离线执行：

```sh
python -m scripts.rebuild_index
```

重建只读取 MySQL 中已完成文档的向量，不调用模型；切块尚未入库或失败任务的部分向量不会被误发布。FlatIP 当前每知识库上限 20 万向量，超出需评估 HNSW 或独立向量服务。

检索使用 FAISS Embedding 语义召回 + jieba/BM25 Okapi 关键词召回 + RRF 排名融合。两路均先应用模型、维度、文档状态和权限/文档范围过滤；BM25 对范围内全部合格切块统计（k1=1.5，b=0.75，正值 IDF），每路最多 60 条。融合公式为 Σ1/(60+rank)，排名从 1 开始，同分按块 ID 排序。`threshold`（默认 0.12）只过滤语义余弦，BM25 独立召回。原始 RRF 分数不表示百分比或正确率。当前 BM25 按请求构建，无缓存，大规模需压测；旧 FULLTEXT 索引保留但不参与当前检索。

每次成功检索（包括零命中）保存记录和片段快照；回放不重新调用模型。删除文档或重新切块会清除实时引用，但保留历史检索快照；删除或清空检索记录会清除这些快照。真实 Agent 之后可通过服务层的 `allowed_kb_ids` 参数限制范围；当前管理页面尚未接入登录与 RBAC。

测试使用模拟模型响应、真实 FAISS 文件和隔离数据库，覆盖批次重试、范围隔离、索引重建、旧版本回滚和检索记录级联行为。真实 MySQL 的在线迁移及用户环境浏览器联调仍需在本机验证。

迁移至最新版本：`python -m alembic upgrade head`（0004）。无需重新向量化或重建 FAISS。新记录 strategy=bm25_rrf；旧记录 legacy_weighted 保留原分数及阈值。返回 bm25_score、semantic_rank、bm25_rank；lexical_score 在新策略中为原始 BM25。

## 政策顾问（LangGraph + Qwen）

已接入 `/api/agents/policy/chat` 与 `/api/agents/policy/config`。LLM 沿用 `.env` 配置，范围由 `POLICY_KB_IDS` 控制（默认 `["general"]`）。图按理解、追问、检索、生成、引用编号检查运行；无有效依据时返回资料不足，不回退演示。当前不流式，政策顾问网页通过会话接口持久化（需迁移0005）；引用编号检查不等于事实核验。详见 [政策顾问实现说明](../docs/项目文档/政策顾问实现说明.md)。无新增数据库迁移，重启后端生效。

## Tavily 联网搜索

在本地 `.env` 填写 `TAVILY_API_KEY=""` 并重启后端即可启用；`.env.example` 保留空白模板。默认 `TAVILY_INCLUDE_DOMAINS=["gov.cn"]`、`TAVILY_MAX_RESULTS=3`、`TAVILY_TIMEOUT_SECONDS=20`。不需要额外 SDK 或数据库迁移。

政策顾问本地零命中、资料不足或涉及时效问题时，执行一次搜索及正文提取，统一交给 Qwen 回答，网页引用附来源链接。Key 未配置或网络失败会明确提示，保留本地证据，不将搜索摘要当作政策原文。取得官方网页不等于已确认政策仍有效；不自动入库。

填 Key 后运行 `python -m scripts.check_tavily` 验证实际搜索与正文提取；该命令会调用 Tavily 服务。

政策顾问现增加 `verify_grounding` 原文一致性辅助检查；通过检查仍不等于权威政策审核。类别区分、审查失败处理、额外模型调用成本及待办见 [优化记录](../docs/项目文档/政策顾问优化记录.md)。无新增数据库迁移。

## 固定政策业务评测

`python -m scripts.evaluate_policy --validate-only` 校验18条固定用例；`python -m scripts.evaluate_policy` 运行16条本地用例；加 `--web` 运行全部18条（会调用真实模型及搜索服务）。报告默认写入被忽略的 `var/evaluations/`，包括完整回答和来源快照。机械断言不代表政策事实准确，仍需人工逐条核对。详见 [评测说明](../docs/项目文档/政策顾问评测说明.md)。

正文批量提取默认超时独立设为60秒（`TAVILY_EXTRACT_TIMEOUT_SECONDS`），搜索仍使用`TAVILY_TIMEOUT_SECONDS`。评测可用`--recheck-report <report.json>`离线复核原回答，不重复消耗模型额度。

网页来源新增截取和完整性元数据，正文提取不等于全文/附件核验。答案会检查无依据的全文缺项判断及“全体”适用范围，限于有限模式和模型辅助审查，不能代替人工审核。

## 政策顾问会话保存

执行 `python -m alembic upgrade head` 升级0005，重启后端后使用新会话接口。问答、来源及审查快照保存在MySQL，回放不请求模型；UUID去重、失败显式重试及单机文件锁保护写入。无状态 `/agents/policy/chat` 保留兼容，评测不写入会话。详见 [会话持久化说明](../docs/项目文档/政策顾问会话持久化说明.md)。
