# FeatureVote

FeatureVote is a lightweight requirement draft pool and task management app built with React, FastAPI, and SQLAlchemy.

The requirement draft pool collects early ideas, votes, and evaluation feedback. Once a draft is accepted, it is converted into a formal task and tracked in task management. Converted drafts remain available for traceability.

## Structure

```text
FeatureVote/
+-- backend/   # FastAPI API
+-- frontend/  # React + Vite app
+-- docs/
+-- scripts/
```

## Backend

The backend exposes a Fider-like product core under `/api/v1`:

- `GET /posts` - list, search, and filter posts
- `POST /posts` - create a post
- `GET /posts/{post_id}` - fetch post detail
- `PATCH /posts/{post_id}` - update post title, description, and existing tags
- `POST /posts/{post_id}/vote` - vote with duplicate-vote protection
- `POST /posts/{post_id}/response` - set status and staff response
- `POST /posts/{post_id}/duplicate` - mark a post as duplicate
- `POST /posts/{post_id}/moderation` - approve or reject a post
- `GET /tags` and `POST /tags` - list and create tags

The first version uses a built-in default tenant. Email, billing, and advanced permission settings are intentionally out of scope.

## Local Development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8090
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Environment

Backend defaults target a local MySQL database named `featurevote`.

```env
APP_NAME=FeatureVote API
APP_ENV=dev
API_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:5173
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=featurevote
```

On startup, SQLAlchemy creates the product-core tables and seeds a default tenant and starter tags.

## Feishu Notifications

Run migrations after deploying notification changes:

```bash
cd backend
python -m alembic upgrade head
```

Requirement draft status changes and task events enqueue Feishu notification tasks. Delivery is processed separately so product actions are not blocked by Feishu failures:

```bash
cd backend
python scripts/process_notifications.py
```

For near-real-time delivery, run the worker in watch mode under systemd or supervisor:

```bash
cd backend
python scripts/process_notifications.py --watch --interval 3
```

The one-shot command is still useful for manual retries. Watch mode keeps polling pending tasks and retries without blocking product actions.

## Feishu Chat Import

Configure one or more Feishu group chats for requirement draft import:

```env
FEISHU_IMPORT_CHAT_IDS=oc_xxx,oc_yyy
FEISHU_IMPORT_INTERVAL_SECONDS=60
# Number of messages requested per Feishu API page (1-50). Import continues through
# all pages within the most recent 90 days.
FEISHU_IMPORT_BATCH_SIZE=50
FEISHU_IMPORT_DEFAULT_TAGS=飞书导入
FEISHU_IMPORT_DUPLICATE_THRESHOLD=0.72
FEISHU_IMPORT_GROUPING_ENABLED=true
FEISHU_IMPORT_WINDOW_MINUTES=60
FEISHU_IMPORT_MIN_CONFIDENCE=0.65
FEISHU_IMPORT_MAX_MESSAGES_PER_SUMMARY=50
FEISHU_IMPORT_DEBUG_LOGGING=false
FEISHU_IMPORT_DEBUG_LOG_MAX_CHARS=4000
```

Run migrations after deploying import changes:

```bash
cd backend
python -m alembic upgrade head
```

Import once:

```bash
cd backend
python scripts/import_feishu_messages.py --once
```

For continuous polling, run it under systemd or supervisor:

```bash
cd backend
python scripts/import_feishu_messages.py --watch --interval 60
```

Admins can also trigger one import pass with `POST /api/v1/feishu-import/run`.

The existing `/posts`, requirement-oriented source directories, and database tables are retained as internal compatibility names. They represent requirement drafts in the product interface.
