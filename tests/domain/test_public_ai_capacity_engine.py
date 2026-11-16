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

    def test_zero_capacity_balance_is_not_reported_as_full_load(self):
        rows = [self.record("a").with_payload({"capacity_units": 0}), self.record("b").with_payload({"capacity_units": 0})]
        balance = forecast_balance(rows)
        self.assertEqual(balance["capacity"], 0.0)
        self.assertIsNone(balance["utilization"])
        self.assertFalse(balance["allocatable"])
        self.assertEqual(balance["capacity_state"], "unavailable")
        self.assertIsNone(balance["overload"])
        self.assertIsNone(shortest_capacity_path(route_graph(rows), "a", "c", 0))

    def test_overload_keeps_ratio_and_shortfall(self):
        rows = [self.record("a").with_payload({"capacity_units": 1, "priority": 40}),
                self.record("b").with_payload({"capacity_units": 1, "priority": 40})]
        balance = forecast_balance(rows)
        self.assertTrue(balance["allocatable"])
        self.assertEqual(balance["capacity_state"], "overloaded")
        self.assertGreater(balance["utilization"], 1.0)
        self.assertGreater(balance["overload"], 0.0)
