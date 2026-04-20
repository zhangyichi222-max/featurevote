# 项目架构设计

## 1. 总体分层

```text
React Web App
      |
      v
FastAPI Backend
      |
      v
SQLite
```

## 2. 前端架构

前端负责页面展示和用户交互，采用 `React + TypeScript + Vite`。

### 目录

```text
frontend/
├── public/
├── src/
│   ├── api/                  # HTTP 请求封装
│   ├── components/           # 通用组件
│   ├── features/
│   │   └── requirements/     # 需求列表、提交、投票、状态更新
│   ├── hooks/                # 状态和请求 hooks
│   ├── pages/                # 页面层
│   ├── types/                # 前端类型定义
│   ├── App.tsx
│   └── main.tsx
└── package.json
```

### 页面拆分

- `RequirementBoardPage`: 需求列表页
- `RequirementSubmitForm`: 提交需求表单
- `RequirementCard`: 单条需求卡片
- `AdminStatusPanel`: 管理员状态更新面板

## 3. 后端架构

后端负责业务规则和 SQLite 数据读写，采用 `FastAPI` 分层设计。

### 目录

```text
backend/
├── app/
│   ├── api/                  # 路由层
│   ├── core/                 # 配置、常量
│   ├── schemas/              # Pydantic 请求/响应模型
│   ├── services/             # 业务逻辑
│   ├── repositories/         # 数据访问抽象
│   └── main.py
├── data/                     # SQLite 数据文件目录
├── requirements.txt
└── .env.example
```

### 模块职责

- `api`: 暴露 REST 接口
- `schemas`: 定义 `requirements`、`votes`、`status update` 数据结构
- `services`: 处理投票去重、票数更新、状态变更
- `repositories`: 封装 SQLite 读写细节，便于未来替换数据库

## 4. 数据流

### 提交需求

1. 前端提交标题和描述
2. 后端写入 `requirements` 表
3. SQLite 返回新记录 ID
4. 前端刷新列表

### 投票

1. 前端发起投票请求
2. 后端检查同一用户是否已对该需求投票
3. 未投票则新增 `votes` 记录
4. 更新 `requirements.vote_count`

### 状态更新

1. 管理员更新状态
2. 后端写回 `requirements.status`
3. 前端重新拉取最新数据

## 5. 建议接口

- `POST /api/v1/requirements`
- `GET /api/v1/requirements`
- `POST /api/v1/requirements/{id}/vote`
- `POST /api/v1/requirements/{id}/status`

## 6. 后续演进

- 增加管理员权限控制
- 引入分页、筛选、排序
- 给 SQLite 补充迁移方案
- 未来如有需要，再替换为更完整的关系型数据库
