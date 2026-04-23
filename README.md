# FeatureVote

FeatureVote is a lightweight Fider-inspired feedback board built with React, FastAPI, and SQLAlchemy.

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
- `POST /posts/{post_id}/vote` - vote with duplicate-vote protection
- `GET /posts/{post_id}/comments` - list comments
- `POST /posts/{post_id}/comments` - create a comment
- `POST /posts/{post_id}/response` - set status and staff response
- `POST /posts/{post_id}/duplicate` - mark a post as duplicate
- `POST /posts/{post_id}/moderation` - approve or reject a post
- `GET /tags` and `POST /tags` - list and create tags

The first version uses a built-in default tenant and demo users. Login, OAuth, email, billing, attachments, notifications, and full admin settings are intentionally out of scope.

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

On startup, SQLAlchemy creates the product-core tables and seeds a default tenant, demo admin, and starter tags.
