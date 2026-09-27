# CLAUDE.md — working notes for AI sessions and the review agent

One page, well under the 6,000-character cap the review agent reads. The setup
guide and the operating notes are in the README.

## What this is

A two-way Jira ↔ Notion sync running on n8n Cloud. One workflow, 26 nodes, two
schedule triggers:

- **Jira → Notion**, every 2 h at :00 — RC1 issues updated in the last 125 min,
  upserted into a Notion database.
- **Notion → Jira**, every 2 h at :15 — status and priority changes pushed back,
  skipping pages the sync itself just wrote.

It also registers as its own error workflow: `Error Trigger` → `Format Error
Message` → a Slack alert.

## Layout

```
workflows/jira_notion_sync.json   the whole thing — the only artifact
tests/test_contract.py            the frozen contract, read from that JSON
docker-compose.yaml               local/self-hosted only, unused on n8n Cloud
.env                              local only, never committed
README.md                         setup, the sync_log table, operating notes
```

The JSON *is* the program; there is no other source tree.

## Conventions (hold a change to these)

- **No secrets in the JSON.** Configuration is n8n Variables
  (`$vars.JIRA_BASE_URL`, `$vars.NOTION_DB_ID`); Jira, Notion and Slack auth are
  n8n credentials referenced by id. A literal key, token or URL with
  credentials in a node is a blocker.
- **Editing this file does nothing to the running instance.** n8n Cloud runs
  its own copy; a change applies only after Workflows → ⋯ → Import from File.
  Review the JSON as a deployment artifact, not as live behavior.
- **Node names are an interface.** The Code nodes reach across the graph by
  name — `$('Loop Over Notion Pages')` in *Map Notion Status → Jira Transition*
  is the load-bearing example. Renaming a node silently breaks every expression
  that referenced it, with no error until the next scheduled run.
- **Echo suppression is a 60-second comparison, and it is what stops a sync
  loop.** `IF — Has Jira Key & Not Echo?` requires
  `last_edited_time - Last Synced > 60000` ms. Loosening or removing that
  condition makes the sync re-process its own writes forever.
- **The 125-minute lookback is deliberately wider than the 2-hour interval** so
  nothing falls between runs. Narrowing it to "match" the schedule reintroduces
  the gap it exists to close.
- **Both directions live in one workflow on purpose**, so the two triggers
  activate and pause together. Splitting them lets one direction run alone,
  which is how a one-way overwrite happens.
- **Logging is best-effort and must stay that way.** The three `sync_log` Data
  Table nodes set `onError: continueRegularOutput` and retry up to 3x, so a
  logging hiccup can never block or fail a sync. A log node that can throw is a
  defect.
- **`sync_log` is the durable system of record**, not `console.log` — console
  output only appears on manual "Test workflow" runs. One `sync_run` row per
  direction with `itemsProcessed`, one `errored` row carrying the failing node
  and message.
- **A missing Jira transition is handled, not assumed.** *Map Notion Status →
  Jira Transition* matches Jira's offered transitions by name substring and
  returns `transitionId: null` when nothing matches; `IF — Valid Transition
  Found?` gates on it. Code that assumed a match would fail a whole run on one
  unmapped status.

## Testing

`pytest` from the repo root (RC1-404) — the contract suite parses the committed
workflow JSON; no network, no n8n, no credentials, and CI runs it on every push
with ruff. It freezes exactly the conventions above: every `$('…')` cross-graph
reference and connection endpoint resolves, echo suppression keeps its 60 s
`gt` comparison, both lookbacks exceed the schedule interval (a relationship,
not a literal), the three log nodes keep `onError: continueRegularOutput` +
retry, no literal secrets, both staggered triggers present, the transition
mapping keeps its `null` fallback and gate. Renaming a referenced node fails
the suite on purpose — update the expression and the test, never delete the
assertion.

The tests prove the JSON, not the deployment: behavior changes are still
unverified until the file is re-imported and a run has been read out of
`sync_log`, and say so rather than implying it was checked.

## Workflow

One branch per ticket, `rc1-NNN-slug`; never commit on `main`. Commit subject
`RC1-NNN: what changed`, short body, **no Co-Authored-By trailer**. Claude opens
the PR; Reid merges. After a JSON change is merged, re-import it in n8n — the
merge alone changes nothing.
