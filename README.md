# Jira ↔ Notion Sync — RC1

Automated two-way sync between Jira project RC1 and a Notion tasks database, powered by n8n.

## What it does

- **Jira → Notion** (every 2 hours, at :00): pulls RC1 issues updated in the last 125 min and upserts them into Notion
- **Notion → Jira** (every 2 hours, at :15): pushes status and priority changes back to Jira, skipping pages the sync itself just wrote (echo suppression)
- **Error alerts**: sends a Slack message if the workflow fails (it is registered as its own error workflow)
- **Audit log**: writes one append-only row per run (and per error) to a `sync_log` n8n Data Table

> Lookback windows (125 min) are deliberately wider than the 2-hour run interval so nothing is missed between runs.
>
> Both directions live in a single n8n workflow with two schedule triggers, so they activate together.

## Prerequisites

This runs on **n8n Cloud**. You'll need:

- An n8n Cloud account and project (Variables and Data Tables, used below, are Cloud features)
- A Jira API token (from id.atlassian.com → Security → API tokens)
- A Notion internal integration token (from notion.so/my-integrations)
- A Slack credential/webhook for error alerts (from api.slack.com/apps)

> The `docker-compose.yaml` and `.env` in this repo are only for running n8n locally/self-hosted. They are not used on n8n Cloud — skip them.

## Setup

> All steps below are done in your n8n Cloud project's web UI.

### 1. Add credentials in n8n

The Notion and Jira calls are made with generic HTTP Request nodes (not the native Notion node), so the credentials are:

Go to Settings → Credentials → New and add:
- **Header Auth** (used for all Notion calls) — header name `Authorization`, value `Bearer <your Notion internal integration token>`
- **Basic Auth** (used for the Jira REST calls) — username = your Atlassian email, password = your Jira API token. Name it something clear like `Jira REST API (Basic Auth)`.
- **Slack API** — your Slack credential/webhook for the error-alert node

### 2. Set workflow variables

The Notion database ID and Jira base URL are read from n8n **Variables** (`$vars`) instead of being hardcoded. In n8n: Settings → Variables → add:

| Variable | Example value |
|---|---|
| `NOTION_DB_ID` | `a6d97762-f3b8-44db-abff-d51688ef6ece` (the UUID from your DB's URL) |
| `JIRA_BASE_URL` | `https://hirereidcollins.atlassian.net` (no trailing slash) |

### 3. Share your Notion database

Open your RC1 Tasks database in Notion → ··· → Connections → add your n8n integration.

### 4. Create the `sync_log` Data Table

In n8n: Data Tables → Create Data Table → name it `sync_log`, then add these columns **exactly** (names and types must match or the log nodes won't bind):

| Column | Type |
|---|---|
| `timestamp` | String |
| `direction` | String |
| `event` | String |
| `level` | String |
| `executionId` | String |
| `itemsProcessed` | Number |
| `detail` | String |

### 5. Import the workflow

In n8n: Workflows → Import from file → select `workflows/jira_notion_sync.json`

Then, after import:
- Wire up the credentials on each HTTP/Slack node (anything with an orange flag).
- Open the three `Log — …` nodes and pick `sync_log` from the Data Table dropdown (they ship with a `REPLACE_WITH_sync_log_TABLE_ID` placeholder).
- Confirm **Settings → Error Workflow** points at this workflow (n8n sometimes reassigns the ID on import).

### 6. Run the initial backfill

Temporarily change the Jira JQL (in the **Jira — Get Updated Issues** node) to:
```
project = RC1 ORDER BY created ASC
```
Click "Test workflow" to populate all existing RC1 tickets into Notion.
Then revert the JQL to `project = RC1 AND updated >= -125m`.

### 7. Activate

Toggle the workflow to **Active**. Both schedule triggers run from this single workflow. Done.

## Observability

Every run appends a row to the `sync_log` Data Table: a `sync_run` row per direction (with `itemsProcessed`) on success, and an `errored` row (with the failing node and message in `detail`) on failure. To audit, open `sync_log` in n8n and filter by `direction` or `level`. The same failures also fire the Slack alert.

The log nodes are best-effort: they continue on error and retry up to 3×, so a logging hiccup can never block or fail a sync.

## Project structure

```
jira-notion-sync/
├── docker-compose.yaml       # local/self-hosted only — unused on n8n Cloud
├── .env.example              # local/self-hosted only — unused on n8n Cloud
├── .env                      # local/self-hosted only (not committed)
├── .gitignore
├── README.md
└── workflows/
    └── jira_notion_sync.json # importable n8n workflow
```

## Operating on n8n Cloud

- **Edit / re-import**: editing `jira_notion_sync.json` on disk does nothing to the running instance — re-import it (Workflows → ⋯ → Import from File) to apply changes.
- **View run history & logs**: open the workflow → Executions tab. `console.log` output only shows there during manual ("Test workflow") runs; the `sync_log` Data Table is your durable system of record.
- **Pause / resume**: toggle the workflow Active switch. Both schedule triggers stop and start together.
