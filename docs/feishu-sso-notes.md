# 飞书免登录接入复盘

本文记录 FeatureVote 对接飞书免登录的接入过程、关键配置、数据库迁移，以及排查中遇到的坑。后续复盘时优先按“排查顺序”从上到下看。

## 目标

用户点击前端“登录飞书用户”按钮后：

1. 前端跳转到后端登录入口。
2. 后端生成飞书 OAuth 授权 URL。
3. 飞书登录成功后回调后端。
4. 后端用 `code` 换取用户信息。
5. 后端创建或更新本地用户，并写入登录 cookie。
6. 浏览器跳回前端。

相关接口：

- `GET /api/v1/auth/feishu/browser/start`
- `GET /api/v1/auth/feishu/browser/callback`
- `GET /api/v1/auth/me`

## 服务器环境变量

服务器上通过 `~/.bashrc` 管理运行配置。后端启动时会从 `~/.bashrc` 读取以下前缀：

- `MYSQL_*`
- `FEISHU_*`
- `FRONTEND_*`

示例：

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=xxx
export MYSQL_DATABASE=featurevote

export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export FEISHU_REDIRECT_URI=http://192.168.200.33:8090/api/v1/auth/feishu/browser/callback

export FRONTEND_BASE_URL=http://192.168.200.33:5173
export FEISHU_ADMIN_USER_NAMES=张三,李四
```

修改后需要：

```bash
source ~/.bashrc
# 重启后端进程
```

注意：如果后端是 systemd、supervisor、Docker 或其他用户启动，必须确认实际运行用户能读到对应 `~/.bashrc`。

## 飞书开放平台配置

在飞书开放平台对应应用中配置：

```text
重定向 URL:
http://192.168.200.33:8090/api/v1/auth/feishu/browser/callback
```

它必须和 `FEISHU_REDIRECT_URI` 完全一致，包括：

- `http` / `https`
- IP 或域名
- 端口
- 路径
- 末尾是否有 `/`

不一致时，飞书会报：

```text
错误码：20029
重定向 URL 有误
```

## 数据库迁移

这次飞书登录需要新增用户字段和归档字段：

- `users.feishu_open_id`
- `users.feishu_union_id`
- `users.email`
- `users.avatar_url`
- `users.department_ids`
- `users.group_ids`
- `users.updated_at`
- `posts.archived_at`
- `posts.archived_by_user_id`

执行迁移：

```bash
cd /data/project/FeatureVote/backend
source ~/.bashrc
source .venv/bin/activate
python -m alembic upgrade head
```

如果遇到旧 Alembic revision：

```text
Can't locate revision identified by '92171358f9e0'
```

说明数据库里的 `alembic_version` 指向旧代码不存在的 revision。处理：

```bash
python -m alembic stamp 202604281730 --purge
python -m alembic upgrade head
```

如果 `stamp --purge` 不支持，可手动改版本：

```bash
mysql -u root -p featurevote -e "UPDATE alembic_version SET version_num='202604281730';"
python -m alembic upgrade head
```

## 管理员设置

最终采用“通过用户名配置管理员”的方式，不依赖飞书部门或群组。

配置：

```bash
export FEISHU_ADMIN_USER_NAMES=张三,李四
```

规则：

- 变量有值时，飞书登录用户名在名单中则为 `admin`。
- 不在名单中则为 `visitor`。
- 变量为空时，不自动改用户角色，保留数据库中已有 `role`。

修改名单后，用户需要重新登录一次，后端才会更新该用户 `role`。

## 踩坑记录

### 1. SQLAlchemy 外键歧义

报错：

```text
AmbiguousForeignKeysError: Could not determine join condition between parent/child tables on relationship UserModel.posts
```

原因：

`posts` 表有两个字段指向 `users.id`：

- `posts.user_id`
- `posts.archived_by_user_id`

SQLAlchemy 不知道 `UserModel.posts` 应该用哪条外键。

处理：

给关系显式指定 `foreign_keys`：

```python
posts = relationship(back_populates="user", foreign_keys="PostModel.user_id")
user = relationship(back_populates="posts", foreign_keys=[user_id])
archived_by = relationship(foreign_keys=[archived_by_user_id])
```

### 2. 登录入口返回 503

现象：

```text
GET /api/v1/auth/feishu/browser/start 503 Service Unavailable
```

原因：

后端没有读到：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_REDIRECT_URI`

处理：

扩展配置加载逻辑，让后端从 `~/.bashrc` 读取 `FEISHU_*`。

### 3. CORS 预检返回 400

现象：

```text
OPTIONS /api/v1/posts 400 Bad Request
OPTIONS /api/v1/auth/me 400 Bad Request
```

原因：

`.env` 中 `CORS_ORIGINS=["http://localhost:5173"]` 的解析方式和当前配置解析不兼容；另外局域网访问前端时 origin 是 `http://192.168.x.x:5173`，没有被放行。

处理：

- `CORS_ORIGINS` 支持逗号列表和 JSON 数组。
- 增加 `CORS_ORIGIN_REGEX`。
- 业务层 `require_mutating_origin()` 也统一使用同一套 origin 判断。

示例：

```bash
export CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
export CORS_ORIGIN_REGEX='^http://192\.168\.[0-9]{1,3}\.[0-9]{1,3}:5173$'
```

### 4. 飞书报“重定向 URL 有误”

报错：

```text
错误码：20029
重定向 URL 有误
```

原因：

后端传给飞书的 `redirect_uri` 没有和飞书后台“重定向 URL”完全一致。

排查方法：

后端在登录入口打印实际使用的回调地址：

```text
Starting Feishu browser login with redirect_uri=...
```

拿日志里的 URL 和飞书后台配置逐字符对比。

### 5. 回调后数据库字段不存在

报错：

```text
Unknown column 'users.feishu_open_id' in 'field list'
Unknown column 'posts.archived_at' in 'field list'
```

原因：

代码已经引用新字段，但 MySQL 老表没有执行迁移。`Base.metadata.create_all()` 只会创建不存在的表，不会给已有表补字段。

处理：

执行：

```bash
python -m alembic upgrade head
```

### 6. Alembic 找不到旧 revision

报错：

```text
Can't locate revision identified by '92171358f9e0'
```

原因：

数据库 `alembic_version` 记录的是旧 revision，但当前代码仓库里已经没有这个迁移文件。

处理：

把数据库迁移版本标记到当前 baseline：

```bash
python -m alembic stamp 202604281730 --purge
python -m alembic upgrade head
```

### 7. MySQL TEXT 字段不能有默认值

报错：

```text
BLOB, TEXT, GEOMETRY or JSON column 'department_ids' can't have a default value
```

原因：

MySQL 不允许 `TEXT NOT NULL DEFAULT ''`。

处理：

迁移改成：

1. 先添加可空 `TEXT` 字段。
2. 更新已有数据为 `''`。
3. 再改成 `NOT NULL`。

迁移还要支持失败后重跑，因为 MySQL DDL 通常不是事务性的，前半段成功后不会自动回滚。

## 快速排查清单

登录失败时按这个顺序查：

1. 后端是否启动成功。
2. `GET /api/v1/auth/feishu/browser/start` 是否返回 307 跳转。
3. 后端日志里的 `redirect_uri` 是否和飞书后台完全一致。
4. 飞书是否能回调到 `/api/v1/auth/feishu/browser/callback`。
5. 数据库是否已执行 `python -m alembic upgrade head`。
6. `users` 表是否有飞书字段。
7. `posts` 表是否有归档字段。
8. CORS 预检是否返回 200。
9. `FEISHU_ADMIN_USER_NAMES` 是否包含当前飞书用户名。

常用检查命令：

```bash
cd /data/project/FeatureVote/backend
source ~/.bashrc
source .venv/bin/activate

python -c "from app.core.config import settings; print(settings.feishu_redirect_uri); print(settings.frontend_base_url); print(settings.feishu_admin_user_names)"
python -m alembic current
python -m alembic heads
```

