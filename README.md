# FeatureVote Demo

一个轻量的需求投票 Demo，采用 `React Web App + FastAPI + SQLite` 的本地闭环架构。

## 目录结构

```text
FeatureVote/
├── backend/                 # FastAPI 后端
├── frontend/                # React Web App 前端
└── docs/
    └── architecture.md      # 架构说明
```

## 核心能力

- 提交需求
- 查看需求列表
- 需求投票
- 管理员更新状态
- 使用 SQLite 持久化保存需求和投票数据

## 快速启动

后端：

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

## 环境变量

后端默认使用本地 SQLite 数据库，配置见 `backend/.env`：

```env
APP_NAME=FeatureVote API
APP_ENV=dev
API_PREFIX=/api/v1
CORS_ORIGINS=["http://localhost:5173"]
SQLITE_DB_PATH=data/featurevote.db
```
