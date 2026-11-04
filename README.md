# 颐养通 · 智能养老服务平台

面向养老院的智能照护与餐食管理项目，将老人档案、账号权限、六类智能体和知识库检索整合到一个平台。当前重点建设“饮食需求核实 → 周菜单编排 → 老人选餐 → 厨房备餐”的业务闭环。

> 项目持续开发中，当前提供本地开发与验证流程。AI 输出需由工作人员结合原始资料核实，不能替代医护判断。

## 当前功能

| 模块 | 已实现能力 |
| --- | --- |
| 账号与权限 | 登录注册、管理员权限、老人账号与档案绑定、本人会话隔离 |
| 老人档案 | 档案新增、查询、编辑、分页及健康和饮食记录维护 |
| 饮食需求 | 选择老人、AI 读取档案并预填、原文依据展示、管理员核实保存 |
| 周菜单 | Agent 生成七天三餐、每餐多套方案、管理员修改、保存、覆盖检查和发布 |
| 老人选餐 | 查看已发布菜单，根据登记条件选餐，截止时间与供应份数限制 |
| 厨房汇总 | 按日期和餐次统计有效选餐，单列未选餐和需复核人员 |
| 六类智能体 | 政策顾问、健康管家、用药管家、膳食营养师、安全守护、心灵陪伴；各模块完成度不同 |
| 知识库与 RAG | 文档批量上传、解析、切块、向量入库、混合检索、索引重建和检索记录 |
| 联网检索 | Tavily 搜索与正文提取，结合来源、地区和证据校验辅助回答 |

餐食流程：

```text
老人档案 → AI 辅助提取饮食要求 → 管理员核实
                                  ↓
Agent 编排周菜单 → 管理员修改 → 覆盖检查 → 发布
                                              ↓
                                        老人确认选餐
                                              ↓
                                        厨房汇总备餐
```

AI 读取档案只预填表单，不自动核实或保存。菜单生成也不会自动发布；发布后的本周菜单冻结。全院覆盖检查用于检查已核实饮食条件的匹配情况，不代表营养达标或供应容量充分。

## 技术栈

- **前端**：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus。
- **后端**：Python 3.11+、FastAPI、SQLAlchemy、Alembic。
- **存储与检索**：MySQL、FAISS、jieba / BM25、RRF 融合。
- **智能体**：LangGraph 流程编排、Qwen 的 OpenAI 兼容接口、Tavily 联网搜索。

MySQL 保存业务数据、文档正文、切块与向量；FAISS 保存派生的向量检索索引。检索采用 Embedding 语义召回 + BM25 关键词召回 + RRF 融合。

## 本地启动

以下命令从仓库根目录执行。需要 MySQL（支持 utf8mb4 和 ngram 全文索引）、Python 3.11+，以及 Node.js `^20.19.0` 或 `>=22.12.0`。

### 1. 后端环境

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

已有 Conda 环境的开发者可使用 `conda activate agent_env`，再安装项目依赖。已有 `.env` 时请保留原配置，按模板补充新增项。

编辑 `backend/.env`，填写 MySQL 连接、模型服务地址和 API Key。主要配置：

| 配置 | 用途 |
| --- | --- |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_DATABASE` | 数据库连接地址与库名 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | 本地数据库账号 |
| `LLM_BASE_URL` / `LLM_API_KEY` | 通用模型服务地址与密钥 |
| `LLM_MODEL` | 通用 Agent 与档案读取，当前配置 `qwen-plus-2025-12-01` |
| `MENU_LLM_MODEL` | 周菜单生成，当前配置 `qwen-plus-2025-07-14`；留空沿用通用模型 |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | 文档与问题向量化服务 |
| `EMBEDDING_DIMENSIONS` | 向量模型实际输出维度，当前项目配置为 1024 |
| `TAVILY_API_KEY` | 联网搜索与正文提取 |
| `HOWTOCOOK_ENABLED` / `HOWTOCOOK_MCP_URL` | 可选的外部食谱 MCP 查询，专属 Streamable HTTP 地址 |

菜单模型与通用模型共用服务地址和 API Key。模型标识需要在所用服务商和账号下可用；修改配置后重启后端。

### 2. 数据库与管理员

先在 MySQL 中创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS yitong_care
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

在 `backend` 目录检查连接并执行迁移：

```bash
python -m scripts.check_db
alembic upgrade head
python -m scripts.setup_admin
```

管理员创建脚本交互输入账号与密码，无内置管理员或默认密码。需要把历史无归属会话归档给管理员时，使用 `python -m scripts.setup_admin --claim-legacy`。老人账号和档案通过管理员绑定，具体步骤见使用说明。

### 3. 启动 API

在 `backend` 目录执行：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/api/health>
- 数据库检查：<http://127.0.0.1:8000/api/health/db>

### 4. 启动前端

另开终端，从仓库根目录执行：

```bash
cd frontend
npm ci
npm run dev
```

打开终端输出的本地地址，默认 <http://127.0.0.1:5173>。开发服务器将 `/api` 代理到本机 8000 端口。前端配置模板见 `frontend/.env.example`。

## 检查与测试

```bash
# 后端：在 backend 目录执行
python -m pytest -q

# 前端：在 frontend 目录执行
npm test
npm run build
```

后端接口测试使用隔离的 SQLite 测试库和模拟模型，不代表真实 MySQL、外部模型与 Tavily 已完成联调。实际连接可使用 `python -m scripts.check_db` 和 `python -m scripts.check_models` 单独检查。

## 目录结构

```text
.
├── backend/
│   ├── app/             # API、智能体、业务服务、模型与数据结构
│   ├── migrations/      # Alembic 数据库迁移
│   ├── scripts/         # 初始化、诊断与评测脚本
│   └── tests/           # 后端单元与接口测试
├── frontend/
│   ├── src/             # 页面、组件、路由和接口封装
│   └── tests/           # 前端测试
└── docs/项目文档/        # 规划、Agent 设计、使用说明、优化记录与架构图
```

## 项目文档

- [文档总目录](docs/项目文档/README.md)
- [养老院升级实施清单](docs/项目文档/01-项目规划/养老院升级实施清单.md)
- [老人账号与档案绑定](docs/项目文档/03-使用说明/老人账号与档案绑定说明.md)
- [每周餐食与老人选餐](docs/项目文档/03-使用说明/每周餐食与老人选餐使用说明.md)
- [智能周菜单生成](docs/项目文档/03-使用说明/智能周菜单生成说明.md)
- [Agent 与 RAG 关系图](docs/项目文档/05-架构图/Agent与RAG关系图.html)

部分文档保留早期实现记录，当前行为以最新说明和代码为准。

## 数据与运行文件

`.env`、密钥、本地虚拟环境、`node_modules`、构建产物及 `backend/var/` 已加入 Git 忽略。`backend/var/` 包含上传原件、FAISS 索引、诊断和评测输出，GitHub 不包含本机数据库和这些运行数据。迁移部署时需单独备份和迁移。

当前账号体系、后台任务和单机文件存储仍处于开发阶段，正式部署配置将后续补充。
