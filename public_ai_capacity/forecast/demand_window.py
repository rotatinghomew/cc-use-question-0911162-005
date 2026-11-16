from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from public_ai_capacity.telemetry.service_event import DomainRecord, bounded, finite_number, normalized_text


@dataclass(frozen=True)
class RouteOption:
    route: tuple[str, ...]
    minutes: float
    cost: float
    capacity_left: float
    cold_chain_risk: float


def route_graph(records: Iterable[DomainRecord]) -> dict[str, list[tuple[str, float, float]]]:
    graph: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for record in records:
        route = normalized_text(record.payload.get("region_code", "origin-destination")).replace("_", "-")
        parts = [part for part in route.split("-") if part]
        if len(parts) < 2:
            parts = ["origin", parts[0] if parts else "destination"]
        eta = max(1.0, finite_number(record.payload.get("latency_ms", 60.0)))
        capacity = max(0.0, finite_number(record.payload.get("capacity_units", 0.0)))
        for left, right in zip(parts, parts[1:]):
            graph[left].append((right, eta / (len(parts) - 1), capacity))
    return graph


def shortest_capacity_path(graph: Mapping[str, list[tuple[str, float, float]]], start: str, end: str,
                           demand: float) -> RouteOption | None:
    queue = [(0.0, start, (start,), float("inf"))]
    seen: dict[str, float] = {}
    while queue:
        minutes, node, route, capacity = heapq.heappop(queue)
        if node == end:
            if capacity <= 0.0:
                return None
            left = max(0.0, capacity - demand)
            return RouteOption(route, minutes, minutes * 0.7 + demand * 1.3, left, 0.0)
        if minutes >= seen.get(node, float("inf")):
            continue
        seen[node] = minutes
        for target, edge_minutes, edge_capacity in graph.get(node, []):
            if edge_capacity <= 0.0 or edge_capacity < demand:
                continue
            heapq.heappush(queue, (minutes + edge_minutes, target, route + (target,), min(capacity, edge_capacity)))
    return None


def journey_pressure(record: DomainRecord) -> dict[str, float]:
    border = bounded(finite_number(record.payload.get("request_queue", 0.0)) / 300.0)
    warehouse = bounded(finite_number(record.payload.get("capacity_load", 0.0)))
    customs = normalized_text(record.payload.get("service_status", "clear"))
    customs_risk = 0.8 if customs not in {"clear", "released", "approved"} else 0.1
    error_rate = finite_number(record.payload.get("error_rate", 20.0))
    cold_risk = bounded(abs(error_rate - 4.0) / 30.0) if normalized_text(record.payload.get("user_group")) in {"cold", "fresh", "medical"} else 0.0
    return {"border": border, "warehouse": warehouse, "customs": customs_risk, "cold": cold_risk,
            "total": bounded(border * .3 + warehouse * .25 + customs_risk * .25 + cold_risk * .2)}


def forecast_balance(records: Iterable[DomainRecord]) -> dict[str, Any]:
    """Aggregate capacity balance for a set of service windows.

    ``utilization`` is only meaningful when at least one capacity unit exists.
    With no available units the ratio is undefined (``None``) and the balance is
    explicitly marked as not allocatable, instead of being clamped to a normal
    "fully loaded" ratio.  When capacity exists but demand exceeds it the raw
    ratio is reported above ``1.0`` and ``overload`` records the shortfall, so
    resource exhaustion stays distinguishable from missing input capacity.
    """
    rows = list(records)
    capacities = [max(0.0, finite_number(row.payload.get("capacity_units", 0.0))) for row in rows]
    demands = [1.0 + max(0.0, finite_number(row.payload.get("priority", 0.0))) for row in rows]
    capacity = sum(capacities)
    demand = sum(demands)
    allocatable = capacity > 0.0
    if allocatable:
        utilization = demand / capacity
        overload = max(0.0, demand - capacity)
        capacity_state = "overloaded" if overload > 0.0 else "balanced"
    else:
        utilization = None
        overload = None
        capacity_state = "unavailable"
    return {"capacity": capacity, "demand": demand,
            "utilization": utilization, "slack": max(0.0, capacity - demand),
            "overload": overload, "allocatable": allocatable,
            "capacity_state": capacity_state}


def derive_context(record: DomainRecord, repository: Any) -> dict[str, Any]:
    rows = repository.list_records() or [record]
    pressure = journey_pressure(record)
    balance = forecast_balance(rows)
    allocatable = balance["allocatable"]
    # Keep the historical bounded ratio for weighting so scenarios that do have
    # capacity keep their previous weights; an unavailable balance is treated as
    # maximally constrained and carries explicit flags instead of a fake ratio.
    bounded_utilization = (bounded(balance["demand"] / max(1.0, balance["capacity"]))
                           if allocatable else 1.0)
    resilience_ratio = (bounded(balance["slack"] / max(1.0, balance["capacity"]))
                        if allocatable else 0.0)
    return {"route_pressure_weight": 0.7 + pressure["total"] * 0.7,
            "eta_reliability_weight": 1.1 - pressure["border"] * 0.4,
            "capacity_balance_weight": 1.1 - bounded_utilization * 0.3,
            "cold_chain_risk_weight": 0.7 + pressure["cold"] * 0.7,
            "forecast_resilience_weight": 0.6 + resilience_ratio * 0.6,
            "capacity_allocatable": allocatable,
            "capacity_utilization": (balance["utilization"] if allocatable else None),
            "capacity_overload": (balance["overload"] if allocatable else None),
            "capacity_state": balance["capacity_state"]}
