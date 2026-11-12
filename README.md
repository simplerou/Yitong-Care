# 禾龄通 · 养老院智能照护协作平台

原名颐养通。保留 `Yitong Care` 目录、数据库和历史标识，避免破坏已有数据及会话。

平台以 **Supervisor 协调六岗位 Agent → 独立图谱规则校验 → 人工审批 → 执行反馈** 为主线。现有老人档案、护工负责关系、周菜单、每日选餐、厨房汇总、知识库、混合检索和历史咨询继续保留。

| 岗位 | 协作工作台能力 | 关键边界 |
| --- | --- | --- |
| 院长 / 管理员 | 审批、运营看板、岗位资质授权、修正台账、审计、知识库管理 | 不直接生成处方或代替专业岗位提交 |
| 医务室 | 核实结构化医护资料，查说明书，生成用药草稿 | 六类白名单工具；有效资质；剂量和冲突由代码校验 |
| 食堂 | 脱敏约束、食物目录、HowToCook、配餐草稿、换餐审批与备餐确认 | 七类工具；不接收老人或药品标识，不读取医务室上下文 |
| 护理部 | 排班草稿、照护上报审核、执行清单与修正跟进 | 有效任职资质；排班冲突由代码检查 |
| 财务部 | 只读工时、代码核薪、工资解释及待审批核薪单 | 不修改排班；缺失打卡单列，不当成零工时 |
| 护工 | 管理负责老人、每日选餐、打卡、照护上报、换餐申请、执行确认 | 逐次核对负责关系；换餐经校验和食堂确认 |

`admin` 对应院长/原管理员，`user` 对应护工；新增 `medical / kitchen / nursing / finance`。注册只能创建护工，其他岗位由院长核实后授权，授权变更会使账号现有会话失效。

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

准备脚本仅补充缺失的协作配置和内部服务令牌，不修改已有模型或数据库密钥。数据库需预先创建，默认保留原 `yitong_care`。新增迁移为 `0017`、`0018`，不删除旧数据。

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

登录后进入“岗位协作”。新账号先注册，再由院长在“岗位与资质”分配岗位。医务室、护理部必须有有效资质记录。

仅用于虚构演示，可显式运行 `python -m scripts.prepare_collaboration --demo`，随后重启校验服务。该模式不需要 Neo4j，所有 `DEMO-*` 数据均为虚构，不能用于实际诊疗或配餐。正式环境默认 `VALIDATION_ALLOW_DEMO=false`。

图事实或独立校验服务不可用时，敏感业务禁止生成草稿，不回退为让模型判断。

## 保留的餐食与知识库流程

护工在“负责老人 → 每日餐食”查看已发布周菜单，为老人选择/修改每日套餐，未启用专业医护档案时结果计入厨房汇总；启用后必须通过协作换餐校验与审批，旧入口不能绕过食药检查。管理员仍负责饮食需求核实、智能周菜单编辑和发布。新协作工作台中的配餐/换餐草稿另走审批及备餐执行单，不会擅自改写已发布周菜单。

MySQL 保存原文、文本块和向量；FAISS 是版本化派生索引。现有混合检索和单库20万向量保护保留。新增药品原文关联：先按 `drug_id`、说明书类别和有效日期过滤，再进行混合检索，引用保留条号、切块位置及原文哈希。Tavily 仍供旧咨询链路查证，不向外发送协作工作台中的患者资料。

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
