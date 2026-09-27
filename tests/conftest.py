"""Shared access to the committed workflow JSON (RC1-404).

Everything is read out of workflows/jira_notion_sync.json at test time. A test
that asserted against a copy of a node would pass forever, including after
someone changed the real one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / "workflows" / "jira_notion_sync.json"

# n8n expressions and Code nodes reach across the graph by node name:
# $('Loop Over Notion Pages'). Renaming the target breaks every one of these
# silently, with no error until the next scheduled run.
CROSS_GRAPH_REF = re.compile(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)")


@pytest.fixture(scope="session")
def raw() -> str:
    return WORKFLOW_PATH.read_text()


@pytest.fixture(scope="session")
def wf(raw) -> dict:
    return json.loads(raw)


@pytest.fixture(scope="session")
def nodes(wf) -> dict[str, dict]:
    by_name = {n["name"]: n for n in wf["nodes"]}
    assert len(by_name) == len(wf["nodes"]), "two nodes share a name"
    return by_name


def strings_in(obj):
    """Every string anywhere inside a node's parameters, however nested."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def cross_graph_refs(node: dict) -> set[str]:
    return {
        ref
        for s in strings_in(node.get("parameters", {}))
        for ref in CROSS_GRAPH_REF.findall(s)
    }


def conditions_of(node: dict) -> list[dict]:
    return node["parameters"]["conditions"]["conditions"]
