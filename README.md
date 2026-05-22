# Jira ↔ Notion Sync — RC1

Automated two-way sync between Jira project RC1 and a Notion tasks database, powered by n8n.

## What it does

- **Jira → Notion** (every 30 min): pulls updated RC1 issues and upserts them into Notion
- **Notion → Jira** (every 30 min, offset by 15 min): pushes status and priority changes back to Jira
- **Error alerts**: sends a Slack message if either workflow fails

## Prerequisites

- Docker + Docker Compose installed
- A Jira API token (from id.atlassian.com → Security → API tokens)
- A Notion internal integration token (from notion.so/my-integrations)
- A Slack incoming webhook URL (from api.slack.com/apps)

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Generate an encryption key and add it to `.env`:

```bash
openssl rand -hex 32
```

### 2. Start n8n

```bash
docker compose up -d
```

Open http://localhost:5678 and create your account.

### 3. Add credentials in n8n

Go to Settings → Credentials → New and add:
- **Jira Software Cloud API** — your email + API token + `hirereidcollins.atlassian.net`
- **Notion API** — your internal integration token
- **Slack API** — your incoming webhook URL

### 4. Share your Notion database

Open your RC1 Tasks database in Notion → ··· → Connections → add your n8n integration.

### 5. Import the workflow

In n8n: Workflows → Import from file → select `workflows/jira_notion_sync.json`

Wire up your credentials to each node (any node with an orange flag).

Set your Notion database ID on all Notion nodes (copy the UUID from your DB's URL).

### 6. Run the initial backfill

Temporarily change the Jira JQL to:
```
project = RC1 ORDER BY created ASC
```
Click "Test workflow" to populate all existing RC1 tickets into Notion.
Then revert the JQL to `project = RC1 AND updated >= -30m`.

### 7. Activate

Toggle both workflows to **Active**. Done.

## Project structure

```
jira-notion-sync/
├── docker-compose.yaml       # n8n container definition
├── .env.example              # environment variable template
├── .env                      # your local config (not committed)
├── .gitignore
├── README.md
└── workflows/
    └── jira_notion_sync.json # importable n8n workflow
```

## Useful commands

```bash
# Start
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f n8n

# Restart
docker compose restart n8n
```
