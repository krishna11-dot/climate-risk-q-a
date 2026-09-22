"""Builds the climate risk knowledge graph from schema.json using NetworkX.

The knowledge graph is the structural anti-hallucination guarantee of this
system: a dataset can only ever be cited if it appears as a node reachable
from the query's hazard/region/scenario path. There is no code path by
which an agent can emit a dataset name that isn't in this graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

import config


def load_schema(schema_path: str | None = None) -> dict[str, Any]:
    """Loads the raw KG schema definition from disk.

    Args:
        schema_path: Path to schema.json. Defaults to config.KG_SCHEMA_PATH.

    Returns:
        The parsed schema dictionary.
    """
    path = Path(schema_path or config.KG_SCHEMA_PATH)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_knowledge_graph(schema_path: str | None = None) -> nx.DiGraph:
    """Builds a directed NetworkX graph encoding hazard -> variable ->
    scenario -> region -> dataset relationships plus region parent edges.

    Node naming convention: every node id is prefixed with its type,
    e.g. "hazard:flood", "region:Kerala", "dataset:CMIP6", to avoid
    collisions between categories that might share a bare name.

    Args:
        schema_path: Path to schema.json. Defaults to config.KG_SCHEMA_PATH.

    Returns:
        A populated networkx.DiGraph.
    """
    schema = load_schema(schema_path)
    graph = nx.DiGraph()

    for hazard in schema["hazards"]:
        graph.add_node(f"hazard:{hazard}", type="hazard", name=hazard)
    for variable in schema["variables"]:
        graph.add_node(f"variable:{variable}", type="variable", name=variable)
    for scenario in schema["scenarios"]:
        graph.add_node(f"scenario:{scenario}", type="scenario", name=scenario)
    for region in schema["regions"]:
        graph.add_node(f"region:{region}", type="region", name=region)
    for dataset in schema["datasets"]:
        graph.add_node(f"dataset:{dataset}", type="dataset", name=dataset)

    for hazard, variable in schema["hazard_variable_map"].items():
        graph.add_edge(f"hazard:{hazard}", f"variable:{variable}", relation="maps_to")

    for child, parent in schema["region_parents"].items():
        graph.add_edge(f"region:{child}", f"region:{parent}", relation="parent_of")

    for scenario, adjacent in schema["scenario_adjacency"].items():
        graph.add_edge(
            f"scenario:{scenario}", f"scenario:{adjacent}", relation="adjacent_to"
        )

    # The dataset for a (scenario, region) pair is stored as data on the
    # scenario->region edge itself, not as a separate region->dataset
    # edge. A region can be reached under multiple scenarios with
    # different datasets (e.g. Global: CMIP6 under SSP5-8.5, ERA5 under
    # SSP1-2.6) — a plain region->dataset edge would merge those into one
    # node with two outgoing edges, and a lookup would arbitrarily return
    # whichever was added first regardless of which scenario asked. This
    # was a real bug, caught by tests/unit/test_kg_query.py once that
    # test's assertion was tightened to check the specific resolved
    # dataset instead of just "found is True".
    scenario_region_dataset: dict[tuple[str, str], str] = {}

    for combo in schema["valid_combinations"]:
        h, v, s, r, d = (
            combo["hazard"],
            combo["variable"],
            combo["scenario"],
            combo["region"],
            combo["dataset"],
        )
        graph.add_edge(f"hazard:{h}", f"variable:{v}", relation="maps_to")
        graph.add_edge(f"variable:{v}", f"scenario:{s}", relation="available_under")

        existing = scenario_region_dataset.get((s, r))
        if existing is not None and existing != d:
            raise ValueError(
                f"schema.json is ambiguous: scenario {s!r} + region {r!r} "
                f"maps to both dataset {existing!r} and {d!r} across "
                "different valid_combinations entries. A (scenario, region) "
                "pair must resolve to exactly one dataset — the graph has "
                "no way to disambiguate further, so this must be fixed in "
                "schema.json, not silently picked one way at query time."
            )
        scenario_region_dataset[(s, r)] = d
        graph.add_edge(
            f"scenario:{s}", f"region:{r}", relation="covers_region", dataset=d
        )

    return graph


_GRAPH_SINGLETON: nx.DiGraph | None = None


def get_graph() -> nx.DiGraph:
    """Returns a process-wide cached instance of the knowledge graph.

    Building the graph is cheap but this avoids re-parsing schema.json
    and re-adding nodes/edges on every query.

    Returns:
        The cached networkx.DiGraph instance.
    """
    global _GRAPH_SINGLETON
    if _GRAPH_SINGLETON is None:
        _GRAPH_SINGLETON = build_knowledge_graph()
    return _GRAPH_SINGLETON
