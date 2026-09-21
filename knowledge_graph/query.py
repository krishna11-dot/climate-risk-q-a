"""Query interface over the NetworkX knowledge graph.

Implements the strict fallback order used by the KG agent:
  1. Exact match: hazard + region + scenario
  2. Parent region node (e.g. Kerala -> South_Asia -> Global)
  3. Adjacent scenario (e.g. SSP3-7.0 -> SSP2-4.5)
  4. Hard stop: coverage_gap=True

This module is the only place in the codebase allowed to resolve a
dataset name. RAG and analysis agents receive datasets exclusively
through this module's return values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from knowledge_graph.builder import get_graph, load_schema


@dataclass
class KGLookupResult:
    """Result of a knowledge graph traversal for a single hazard query.

    Attributes:
        found: True if a valid path to a dataset was found.
        hazard: The hazard queried.
        variable: The climate variable associated with the hazard.
        scenario: The scenario actually used (may differ from requested
            if adjacency fallback fired).
        region: The region actually used (may be a parent of the
            requested region if fallback fired).
        parent_region: The immediate parent of the originally requested
            region, always populated when available, for SQL widening.
        dataset: The resolved dataset name, drawn only from KG nodes.
        fallback_used: Which fallback tier resolved the query
            ("exact", "parent_region", "adjacent_scenario", or None).
        coverage_gap: True if no path could be found through any fallback.
        nodes_traversed: Ordered list of KG node ids visited, shown to
            the user in the UI to make the anti-hallucination path visible.
    """

    found: bool
    hazard: str
    variable: str | None = None
    scenario: str | None = None
    region: str | None = None
    parent_region: str | None = None
    dataset: str | None = None
    fallback_used: str | None = None
    coverage_gap: bool = False
    nodes_traversed: list[str] = field(default_factory=list)


def _get_parent_region(graph: nx.DiGraph, region: str) -> str | None:
    node = f"region:{region}"
    if node not in graph:
        return None
    for _, target, data in graph.out_edges(node, data=True):
        if data.get("relation") == "parent_of":
            return graph.nodes[target]["name"]
    return None


def _get_adjacent_scenario(graph: nx.DiGraph, scenario: str) -> str | None:
    node = f"scenario:{scenario}"
    if node not in graph:
        return None
    for _, target, data in graph.out_edges(node, data=True):
        if data.get("relation") == "adjacent_to":
            return graph.nodes[target]["name"]
    return None


def _resolve_dataset(
    graph: nx.DiGraph, hazard: str, scenario: str, region: str
) -> tuple[str | None, str | None, list[str]]:
    """Attempts a single exact traversal hazard -> variable -> scenario ->
    region -> dataset.

    Returns:
        Tuple of (variable, dataset, nodes_traversed). dataset is None
        if no path exists for this exact combination.
    """
    schema = load_schema()
    variable = schema["hazard_variable_map"].get(hazard)
    if variable is None:
        return None, None, []

    nodes = [f"hazard:{hazard}", f"variable:{variable}"]
    scenario_node = f"scenario:{scenario}"
    region_node = f"region:{region}"

    if scenario_node not in graph or region_node not in graph:
        return variable, None, nodes

    if not graph.has_edge(f"variable:{variable}", scenario_node):
        return variable, None, nodes
    nodes.append(scenario_node)

    if not graph.has_edge(scenario_node, region_node):
        return variable, None, nodes
    nodes.append(region_node)

    dataset_node = None
    for _, target, data in graph.out_edges(region_node, data=True):
        if data.get("relation") == "sourced_from":
            dataset_node = target
            break

    if dataset_node is None:
        return variable, None, nodes
    nodes.append(dataset_node)
    dataset_name = graph.nodes[dataset_node]["name"]
    return variable, dataset_name, nodes


def lookup(hazard: str, region: str, scenario: str) -> KGLookupResult:
    """Resolves hazard/region/scenario to a dataset using the KG, applying
    the strict fallback order on failure.

    Args:
        hazard: One of the hazards in schema.json (e.g. "flood").
        region: One of the regions in schema.json (e.g. "Kerala").
        scenario: One of the scenarios in schema.json (e.g. "SSP5-8.5").

    Returns:
        A KGLookupResult describing what was found (or the coverage gap).
    """
    graph = get_graph()
    parent_region = _get_parent_region(graph, region)

    # 1. Exact match.
    variable, dataset, nodes = _resolve_dataset(graph, hazard, scenario, region)
    if dataset:
        return KGLookupResult(
            found=True,
            hazard=hazard,
            variable=variable,
            scenario=scenario,
            region=region,
            parent_region=parent_region,
            dataset=dataset,
            fallback_used="exact",
            nodes_traversed=nodes,
        )

    # 2. Parent region fallback, walking up the chain to Global.
    current_region = parent_region
    while current_region:
        variable, dataset, fallback_nodes = _resolve_dataset(
            graph, hazard, scenario, current_region
        )
        if dataset:
            return KGLookupResult(
                found=True,
                hazard=hazard,
                variable=variable,
                scenario=scenario,
                region=current_region,
                parent_region=parent_region,
                dataset=dataset,
                fallback_used="parent_region",
                nodes_traversed=fallback_nodes,
            )
        current_region = _get_parent_region(graph, current_region)

    # 3. Adjacent scenario fallback (tried against the original region).
    adjacent_scenario = _get_adjacent_scenario(graph, scenario)
    if adjacent_scenario:
        variable, dataset, fallback_nodes = _resolve_dataset(
            graph, hazard, adjacent_scenario, region
        )
        if dataset:
            return KGLookupResult(
                found=True,
                hazard=hazard,
                variable=variable,
                scenario=adjacent_scenario,
                region=region,
                parent_region=parent_region,
                dataset=dataset,
                fallback_used="adjacent_scenario",
                nodes_traversed=fallback_nodes,
            )

    # 4. Hard stop.
    return KGLookupResult(
        found=False,
        hazard=hazard,
        variable=variable,
        scenario=scenario,
        region=region,
        parent_region=parent_region,
        dataset=None,
        fallback_used=None,
        coverage_gap=True,
        nodes_traversed=nodes,
    )


def verify_dataset_in_kg(dataset_name: str) -> bool:
    """Verifies that a dataset name exists as a node in the knowledge
    graph. Used by output_filter.py to guarantee zero hallucinated
    dataset citations.

    Args:
        dataset_name: The dataset name to verify (e.g. "CMIP6").

    Returns:
        True if the dataset exists as a KG node, False otherwise.
    """
    graph = get_graph()
    return f"dataset:{dataset_name}" in graph
