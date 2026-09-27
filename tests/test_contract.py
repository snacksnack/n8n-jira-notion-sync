"""The workflow's frozen contract (RC1-404).

This workflow runs unattended every 2 hours on n8n Cloud, and its failure modes
do not raise: a renamed node breaks a cross-graph expression with no error until
the next scheduled run; a loosened echo-suppression condition makes the sync
reprocess its own writes forever. These tests are what stands between an edit
and either of those. Renaming a node referenced across the graph fails here on
purpose — update the expression and the test, do not delete the assertion.
"""

from __future__ import annotations

import re

from conftest import conditions_of, cross_graph_refs, strings_in

# --- cross-graph references — the highest-value check ----------------------


def test_every_cross_graph_reference_targets_a_real_node(nodes):
    """$('Name') in a Code node or expression is a lookup by node name.

    n8n does not validate these on import; the first sign of a broken one is
    the next scheduled run failing (or worse, half-running).
    """
    for name, node in nodes.items():
        for ref in cross_graph_refs(node):
            assert ref in nodes, (
                f"{name!r} reaches for $({ref!r}), but no node has that name — "
                "a rename broke this expression"
            )


def test_the_load_bearing_reference_is_still_seen_by_the_scan(nodes):
    """Guards the scanner itself: if the regex rotted, the test above would
    pass by finding nothing. The known cross-graph hop must be among the
    matches."""
    refs = cross_graph_refs(nodes["Map Notion Status → Jira Transition"])
    assert "Loop Over Notion Pages" in refs


def test_every_connection_endpoint_is_a_real_node(wf, nodes):
    for source, outputs in wf["connections"].items():
        assert source in nodes, f"connections entry {source!r} names a missing node"
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in nodes, (
                    f"{source!r} connects to missing node {target['node']!r}"
                )


# --- echo suppression — the only thing preventing a sync loop --------------


def test_echo_suppression_still_compares_against_60_seconds(nodes):
    """Notion → Jira must skip pages the sync itself just wrote. The IF node
    requires last_edited_time to be more than 60s after Last Synced; loosening
    or removing this makes the sync reprocess its own writes forever."""
    conds = conditions_of(nodes["IF — Has Jira Key & Not Echo?"])
    echo = [c for c in conds if "last_edited_time" in c["leftValue"]]
    assert len(echo) == 1, "the echo-suppression condition is gone"
    (echo,) = echo
    assert "Last Synced" in echo["leftValue"], "no longer compared against Last Synced"
    assert echo["operator"] == {"type": "number", "operation": "gt"}
    assert echo["rightValue"] == 60000, "the 60-second window moved"


def test_echo_suppression_also_requires_a_jira_key(nodes):
    node = nodes["IF — Has Jira Key & Not Echo?"]
    conds = conditions_of(node)
    key = [c for c in conds if "Jira Key" in c["leftValue"]]
    assert len(key) == 1 and key[0]["operator"]["operation"] == "notEmpty"
    assert node["parameters"]["conditions"]["combinator"] == "and", (
        "with OR, a page without a Jira Key would slip through on recency alone"
    )


# --- the lookback must exceed the schedule interval -------------------------


def _interval_minutes(cron: str) -> int:
    """Both triggers run on an every-N-hours cron (`M */N * * *`)."""
    hour = cron.split()[1]
    step = re.fullmatch(r"\*/(\d+)", hour)
    assert step, f"cron {cron!r} is no longer an every-N-hours schedule"
    return int(step.group(1)) * 60


def test_jira_lookback_exceeds_the_schedule_interval(nodes):
    """125 minutes against a 2-hour interval, asserted as a relationship so
    'tidying' the lookback to match the schedule fails — narrowing it
    reintroduces the between-runs gap it exists to close."""
    interval = _interval_minutes(
        nodes["Every 2 h at :00 (Jira → Notion)"]["parameters"]["rule"]["interval"][0][
            "expression"
        ]
    )
    jql = nodes["Jira — Get Updated Issues"]["parameters"]["options"]["jql"]
    lookback = re.search(r"updated >= -(\d+)m", jql)
    assert lookback, f"the JQL lost its relative lookback: {jql!r}"
    assert int(lookback.group(1)) > interval


def test_notion_lookback_exceeds_the_schedule_interval(nodes):
    interval = _interval_minutes(
        nodes["Every 2 h at :15 (Notion → Jira)"]["parameters"]["rule"]["interval"][0][
            "expression"
        ]
    )
    body = nodes["Notion — Get Changed Pages"]["parameters"]["jsonBody"]
    lookback = re.search(r"\$now\.minus\((\d+), 'minutes'\)", body)
    assert lookback, f"the Notion query lost its relative lookback: {body!r}"
    assert int(lookback.group(1)) > interval


# --- logging must never fail a sync -----------------------------------------


def test_all_three_log_nodes_exist_and_cannot_fail_the_run(wf):
    """sync_log is best-effort by construction: onError continues the run and
    failures retry. A log node that can throw turns a logging hiccup into a
    failed sync."""
    log_nodes = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.dataTable"]
    assert {n["name"] for n in log_nodes} == {
        "Log — Jira→Notion Run",
        "Log — Notion→Jira Run",
        "Log — Errored",
    }
    for n in log_nodes:
        assert n.get("onError") == "continueRegularOutput", f"{n['name']} can fail the sync"
        assert n.get("retryOnFail") is True, f"{n['name']} no longer retries"


# --- no literal secrets ------------------------------------------------------


def test_configuration_still_comes_from_n8n_variables(raw):
    assert "$vars.JIRA_BASE_URL" in raw
    assert "$vars.NOTION_DB_ID" in raw


def test_no_literal_tokens_or_credentialed_urls(raw):
    """Auth belongs in n8n credentials (referenced by id) and $vars. A literal
    key, token, or user:pass URL in the JSON is a blocker."""
    for pattern, what in [
        (r"xox[bpars]-", "a Slack token"),
        (r"ATATT[A-Za-z0-9]", "an Atlassian API token"),
        (r"secret_[A-Za-z0-9]{20}", "a Notion integration token"),
        (r"ntn_[A-Za-z0-9]", "a Notion integration token"),
        (r"Bearer [A-Za-z0-9]", "a bearer token"),
        (r"https?://[^\s\"'/]+:[^\s\"'@/]+@", "credentials inside a URL"),
    ]:
        assert not re.search(pattern, raw), f"the workflow JSON appears to contain {what}"


def test_credentials_are_referenced_by_id_only(nodes):
    for name, node in nodes.items():
        for cred in node.get("credentials", {}).values():
            assert set(cred) == {"id", "name"}, (
                f"{name!r} embeds credential material instead of a reference"
            )


# --- both directions live in one workflow ------------------------------------


def test_both_schedule_triggers_are_present_and_staggered(wf, nodes):
    """Splitting the directions lets one run alone — which is how a one-way
    overwrite happens. Both triggers also must not fire at the same minute:
    the :15 offset is what lets Jira → Notion finish first."""
    triggers = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger"]
    assert len(triggers) == 2, "one direction's trigger is missing (or a third appeared)"
    offsets = {
        t["parameters"]["rule"]["interval"][0]["expression"].split()[0] for t in triggers
    }
    assert len(offsets) == 2, "the two triggers fire at the same minute"


def test_each_trigger_feeds_its_own_direction(wf):
    conns = wf["connections"]
    assert (
        conns["Every 2 h at :00 (Jira → Notion)"]["main"][0][0]["node"]
        == "Jira — Get Updated Issues"
    )
    assert (
        conns["Every 2 h at :15 (Notion → Jira)"]["main"][0][0]["node"]
        == "Notion — Get Changed Pages"
    )


# --- the transition mapping degrades safely ----------------------------------


def test_unmapped_status_yields_null_not_an_error(nodes):
    """One Notion status with no matching Jira transition must skip that page,
    not fail the whole run. The Code node returns transitionId: null and the
    IF node gates on it."""
    js = nodes["Map Notion Status → Jira Transition"]["parameters"]["jsCode"]
    assert "transitionId: match ? match.json.id : null" in js, (
        "the null fallback is gone — an unmapped status would now fail the run"
    )


def test_the_valid_transition_gate_checks_transition_id(nodes, wf):
    conds = conditions_of(nodes["IF — Valid Transition Found?"])
    assert any(
        "$json.transitionId" in c["leftValue"] and c["operator"]["operation"] == "notEmpty"
        for c in conds
    ), "the gate no longer checks transitionId"
    assert (
        wf["connections"]["Map Notion Status → Jira Transition"]["main"][0][0]["node"]
        == "IF — Valid Transition Found?"
    ), "the mapping's output no longer flows through the gate"


# --- the error path stays wired ----------------------------------------------


def test_a_failure_alerts_slack_and_logs(wf, nodes):
    """The workflow registers as its own error workflow; a broken error path
    means failures become invisible, which is this repo's defining risk."""
    targets = {t["node"] for t in wf["connections"]["Format Error Message"]["main"][0]}
    assert targets == {"Slack — Send Error Alert", "Log — Errored"}
    assert (
        wf["connections"]["Error Trigger"]["main"][0][0]["node"] == "Format Error Message"
    )


def test_scanner_sees_expressions_everywhere(nodes):
    """Meta-check: strings_in must keep reaching nested parameters (jsonBody,
    pagination options, condition values), or several tests above would pass
    vacuously after an n8n schema change."""
    everything = [s for n in nodes.values() for s in strings_in(n.get("parameters", {}))]
    assert any("$now.minus(" in s for s in everything)
    assert any("start_cursor" in s for s in everything)
