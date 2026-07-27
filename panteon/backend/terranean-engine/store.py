from typing import Any
from models import Event


class Store:
    def __init__(self):
        self.events: dict[str, Event] = {}
        self.causal_graph: Any = None
        self.purposes: dict[str, dict] = {}
        self.trajectories: dict[str, dict] = {}

    def add_events(self, events: list[Event]):
        for e in events:
            self.events[e.id] = e

    def get_events(self, scope: str | None = None) -> list[Event]:
        events = list(self.events.values())
        if scope:
            events = [e for e in events if scope in e.actor or scope in (e.target or "")]
        return sorted(events, key=lambda e: e.timestamp)

    def clear(self):
        self.events.clear()
        self.causal_graph = None
        self.purposes.clear()
        self.trajectories.clear()


store = Store()
