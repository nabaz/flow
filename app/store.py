from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RouteStats:
    total_matched: int = 0
    total_routed: int = 0
    total_suppressed: int = 0


@dataclass
class StatsAccumulator:
    total_alerts_processed: int = 0
    total_routed: int = 0
    total_suppressed: int = 0
    total_unrouted: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_route: dict[str, RouteStats] = field(default_factory=dict)
    by_service: dict[str, int] = field(default_factory=dict)

    def record(self, alert_severity: str, alert_service: str, winner_id: str | None, suppressed: bool) -> None:
        self.total_alerts_processed += 1
        self.by_severity[alert_severity] = self.by_severity.get(alert_severity, 0) + 1
        self.by_service[alert_service] = self.by_service.get(alert_service, 0) + 1

        if winner_id is None:
            self.total_unrouted += 1
            return

        if winner_id not in self.by_route:
            self.by_route[winner_id] = RouteStats()
        rs = self.by_route[winner_id]
        rs.total_matched += 1

        if suppressed:
            self.total_suppressed += 1
            rs.total_suppressed += 1
        else:
            self.total_routed += 1
            rs.total_routed += 1


class Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.routes: dict[str, Any] = {}          # route_id -> RouteInput
        self.alerts: dict[str, Any] = {}          # alert_id -> AlertResult dict
        self.alert_inputs: dict[str, Any] = {}    # alert_id -> AlertInput
        # (service, route_id) -> expiry datetime (tz-aware)
        self.suppression: dict[tuple[str, str], datetime] = {}
        self.stats = StatsAccumulator()


store = Store()
