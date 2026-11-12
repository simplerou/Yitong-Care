# 禾龄通 · 养老院智能照护协作平台

原名颐养通。保留 `Yitong Care` 目录、数据库和历史标识，避免破坏已有数据及会话。

平台以 **Supervisor 协调六岗位 Agent → 独立图谱规则校验 → 人工审批 → 执行反馈** 为主线。当前只开放六岗位职责入口。历史咨询、知识库和餐食数据保留，旧咨询 Agent 与维护页面退出正常业务入口。

| 岗位 | 协作工作台能力 | 关键边界 |
| --- | --- | --- |
| 院长 / 管理员 | 运营看板、业务审批、注册审核与账号启停 | 不读取病历明细、不维护老人档案、不分配护工 |
| 医务室 | 核实结构化医护资料，查说明书，生成用药草稿 | 六类白名单工具；有效资质；剂量和冲突由代码校验 |
| 食堂 | 脱敏约束、食物目录、HowToCook、配餐草稿、换餐审批与备餐确认 | 七类工具；不接收老人或药品标识，不读取医务室上下文 |
| 护理部 | 护工负责分配、老人建档维护、排班草稿、照护上报审核 | 有效任职资质；排班冲突由代码检查 |
| 财务部 | 只读工时、代码核薪、工资解释及待审批核薪单 | 不修改排班；缺失打卡单列，不当成零工时 |
| 护工 | 只读负责老人和每日餐食、打卡、异常上报、换餐校验、执行确认 | 逐次核对负责关系；不能编辑档案、剂量或直接改餐；换餐须食堂审批 |

`admin` 对应院长/原管理员，`user` 对应护工；新增 `medical / kitchen / nursing / finance`。注册时申请护工、医务室、食堂、护理部或财务部岗位，审核前只可查看申请状态；院长核实后开通，原申请会话失效。未通过可补充资料重申，支持离职停用与恢复。既有账号继续使用。

## 实现结构

```text
Vue 六岗位工作台
    ↓ 每次请求重新解析身份和资质
FastAPI 岗位网关 → LangGraph Supervisor → 独立上下文的岗位子图
    ↓ 查证 / 严格 Schema / 校验 / 整理 / 复校
MySQL 持久化待确认草稿、原始建议和修正记录
    ↓ 版本、时效、权限、源指纹、规则与图事实再次核验
审批 → 配餐 / 用药执行单、排班、核薪确认 → 执行反馈

独立校验服务：FastAPI 或 MCP stdio
    ↓ 固定参数化 Cypher（Agent 无任意图查询工具）
Neo4j：药品 → 活性成分 → 冲突规则 → 冲突成分 ← 食材
    ↓ 证据节点、条号、原文位置
Decimal 剂量 / 营养计算及冲突判定
```

技术栈：FastAPI、SQLAlchemy、Alembic、MySQL、LangGraph、Qwen、Neo4j/Cypher、FAISS + 中文 BM25 + RRF、MCP、Vue 3 + TypeScript。

## 本地启动

需要 Python 3.11+（可使用现有 `agent_env`）、MySQL、Node 20.19+/22.12+、Neo4j 5 的 HTTP 端口。

在 `backend` 目录：

```bash
python -m pip install -e '.[dev]'
# 没有 .env 时才从 .env.example 复制；已有配置不要覆盖。
python -m scripts.prepare_collaboration
python -m scripts.check_db
alembic upgrade head
python -m scripts.setup_admin
```

准备脚本仅补充缺失的协作配置和内部服务令牌，不修改已有模型或数据库密钥。数据库需预先创建，默认保留原 `yitong_care`。新增迁移为 `0017`、`0018`、`0019`、`0020`，不删除旧数据。

在 `backend/.env` 配置 `NEO4J_HTTP_URL / NEO4J_DATABASE / NEO4J_USER / NEO4J_PASSWORD`，再导入**经专业核实**的图事实：

```bash
python -m scripts.import_validation_graph /path/to/reviewed-facts.json
python -m scripts.import_validation_graph /path/to/reviewed-facts.json --apply --reviewer '核实责任人'
```

分别启动：

```bash
# 终端1，backend 目录
uvicorn validation_service.main:app --host 127.0.0.1 --port 8100
# 终端2，backend 目录
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 终端3，frontend 目录
npm ci
npm run dev
```

登录后进入“岗位协作”。新账号先申请岗位，再由院长在“注册审核”核实开通。医务室、护理部必须有有效资质记录。

仅用于虚构演示，可显式运行 `python -m scripts.prepare_collaboration --demo`，随后重启校验服务。该模式不需要 Neo4j，所有 `DEMO-*` 数据均为虚构，不能用于实际诊疗或配餐。正式环境默认 `VALIDATION_ALLOW_DEMO=false`。

图事实或独立校验服务不可用时，敏感业务禁止生成草稿，不回退为让模型判断。

## 当前业务与历史资料

护理部维护老人档案、分配已开通护工；护工只查看负责老人。换餐通过代码校验、食堂批准和备餐确认后才进入护工执行。照护上报由护理部审核，同时进入医务室异常待办。原周菜单只读资料保留，直接选改套餐、周菜单管理和旧六类咨询不再开放。当前食堂协作草稿是一日配餐，不自动改写历史周菜单。

MySQL 保存原文、文本块和向量；FAISS 是派生索引。混合检索仍供内部说明书查证使用，知识库/RAG管理接口退出正常岗位入口，原始数据和历史咨询没有删除。HowToCook 供食堂查食谱参考。

岗位菜单、接口边界和完整协作流程见[六岗位职责与入口收敛说明](docs/项目文档/02-Agent设计/六岗位职责与入口收敛说明.md)。

## 测试与评测

```bash
# backend
python -m pytest -q
python -m scripts.evaluate_collaboration --fixture
python -m scripts.evaluate_collaboration --fixture --split holdout
# frontend
npm test
npm run build
```

固定集区分校准和保留样本，报告实际通过/失败/阻塞。它不是临床盲试或生产效果报告。简历中的 Recall@10≈85%、工具成功率≈95%、节时≈30%需要独立数据和一致口径复测，当前实现不将这些数字当作已验证结果。

## 部署与文档

本地独立容器栈见 [compose.yml](compose.yml)，需额外配置独立容器数据库密码及 Neo4j 密码；不会迁入或覆盖宿主机原 MySQL 数据：

```bash
docker compose --env-file backend/.env up --build -d
docker compose exec api python -m scripts.setup_admin
```

首次启动后还需为 Neo4j 导入核实事实。当前环境未实际拉取镜像或部署外部服务。

- [完整实现与验收说明](docs/项目文档/03-使用说明/禾龄通六岗位协作完整使用与验收说明.md)
- [简历 v16 需求对照与验证记录](docs/项目文档/04-优化与评测/简历v16实现对照与验证记录.md)
- [项目文档导航](docs/项目文档/README.md)

配置密钥、数据库内容、音频、索引文件、日志和诊断报告不提交 GitHub。代码目录继续使用原名，项目展示名称已更新为禾龄通。

注册与审核步骤见[员工注册与岗位审核说明](docs/项目文档/03-使用说明/员工注册与岗位审核说明.md)。

现行Agent职责及真实Function Calling用法见[岗位Agent职责修订](docs/项目文档/02-Agent设计/岗位Agent职责与ReAct调用说明.md)，其中用药必须医生签字后进入院长审批，护工不再有业务编辑权。
