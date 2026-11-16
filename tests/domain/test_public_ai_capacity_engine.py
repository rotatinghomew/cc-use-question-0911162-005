from __future__ import annotations

import unittest
from public_ai_capacity.telemetry.service_event import DomainRecord
from public_ai_capacity.forecast.demand_window import journey_pressure, forecast_balance, route_graph, shortest_capacity_path


class CapacityReplayTests(unittest.TestCase):
    def record(self, key, route="a-b-c"):
        return DomainRecord(key, {"service_id": key, "region_code": route, "priority_class": "truck", "user_group": "cold",
            "latency_ms": 120, "request_queue": 20, "capacity_load": .6, "error_rate": 7,
            "service_status": "clear", "capacity_units": 10, "priority": 2, "event_sequence": 1})

    def test_graph_path_respects_capacity(self):
        graph = route_graph([self.record("s1")])
        self.assertIsNotNone(shortest_capacity_path(graph, "a", "c", 5))
        self.assertIsNone(shortest_capacity_path(graph, "a", "c", 50))

    def test_pressure_and_balance(self):
        rows = [self.record("a"), self.record("b")]
        self.assertGreater(journey_pressure(rows[0])["total"], 0.0)
        self.assertGreater(forecast_balance(rows)["capacity"], forecast_balance(rows)["demand"])
