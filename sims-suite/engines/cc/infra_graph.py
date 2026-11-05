"""CC infrastructure graph — your stack as a graph of nodes and edges.

Each node is a service (API, database, load balancer, message queue, etc.)
with a criticality score and a set of vulnerabilities. Each edge is a
dependency or trust relationship. Collective Consciousness runs attack paths through this
graph the same way Kriegspiel runs forces across a battlefield.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeType(str, Enum):
    API_GATEWAY = "api_gateway"
    WEB_SERVER = "web_server"
    DATABASE = "database"
    MESSAGE_QUEUE = "message_queue"
    LOAD_BALANCER = "load_balancer"
    CDN = "cdn"
    AUTH_SERVICE = "auth_service"
    CACHE = "cache"
    WORKER = "worker"
    STORAGE = "storage"
    DNS = "dns"
    FIREWALL = "firewall"
    MONITORING = "monitoring"
    THIRD_PARTY = "third_party"


class Vulnerability(str, Enum):
    """Vulnerability classes that enable attack-path progression."""

    OPEN_PORTS = "open_ports"
    WEAK_AUTH = "weak_auth"
    UNPATCHED_SOFTWARE = "unpatched_software"
    MISCONFIGURATION = "misconfiguration"
    EXPOSED_CREDENTIALS = "exposed_credentials"
    OVERPERMISSIONED = "overpermissioned"
    NO_ENCRYPTION = "no_encryption"
    LOG_INJECTION = "log_injection"
    SSRF = "ssrf"
    DESERIALIZATION = "deserialization"
    SQL_INJECTION = "sql_injection"
    MISSING_PATCH = "missing_patch"


@dataclass
class InfraNode:
    """A service in your infrastructure."""

    name: str
    node_type: NodeType
    criticality: float = 50.0          # 0-100, how bad if this falls
    exposure: float = 30.0             # 0-100, how reachable from outside
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    is_external: bool = False          # internet-facing?
    is_crown_jewel: bool = False       # if this falls, the game is over

    @property
    def attack_surface(self) -> float:
        """How easy this node is to compromise (0-100)."""
        vuln_score = len(self.vulnerabilities) * 12
        return min(100, self.exposure + vuln_score)

    @property
    def defense_score(self) -> float:
        """How hard this node is to compromise (0-100)."""
        return 100 - self.attack_surface


@dataclass
class InfraEdge:
    """A dependency or trust relationship between two nodes."""

    source: str                        # node name
    target: str                        # node name
    trust_level: float = 50.0          # 0-100, how much access the source has to target
    is_bidirectional: bool = False


@dataclass
class InfraGraph:
    """A complete infrastructure topology."""

    name: str
    nodes: dict[str, InfraNode] = field(default_factory=dict)
    edges: list[InfraEdge] = field(default_factory=list)

    def add_node(self, node: InfraNode) -> None:
        self.nodes[node.name] = node

    def add_edge(self, edge: InfraEdge) -> None:
        self.edges.append(edge)

    def neighbors(self, node_name: str) -> list[tuple[str, float]]:
        """Return (neighbor_name, trust_level) pairs reachable from a node."""
        result = []
        for edge in self.edges:
            if edge.source == node_name:
                result.append((edge.target, edge.trust_level))
            elif edge.is_bidirectional and edge.target == node_name:
                result.append((edge.source, edge.trust_level))
        return result

    def crown_jewels(self) -> list[str]:
        """Names of nodes marked as crown jewels."""
        return [n.name for n in self.nodes.values() if n.is_crown_jewel]

    def to_geojson(self) -> dict:
        """Render as a node-link diagram for the dashboard (uses GeoJSON-like features)."""
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {
                        "name": n.name,
                        "node_type": n.node_type.value,
                        "criticality": n.criticality,
                        "exposure": n.exposure,
                        "attack_surface": round(n.attack_surface, 1),
                        "is_external": n.is_external,
                        "is_crown_jewel": n.is_crown_jewel,
                        "vulnerabilities": [v.value for v in n.vulnerabilities],
                    },
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "trust": e.trust_level}
                for e in self.edges
            ],
        }


# --- Predefined infrastructure templates ---

def create_sample_infra(name: str = "Production Stack") -> InfraGraph:
    """Create a representative production infrastructure graph."""
    graph = InfraGraph(name=name)

    nodes = [
        InfraNode("Internet Gateway", NodeType.FIREWALL, criticality=90, exposure=100,
                  is_external=True, vulnerabilities=[Vulnerability.OPEN_PORTS]),
        InfraNode("Load Balancer", NodeType.LOAD_BALANCER, criticality=85, exposure=80,
                  vulnerabilities=[Vulnerability.MISCONFIGURATION]),
        InfraNode("Web API", NodeType.WEB_SERVER, criticality=70, exposure=60,
                  vulnerabilities=[Vulnerability.UNPATCHED_SOFTWARE, Vulnerability.WEAK_AUTH]),
        InfraNode("Auth Service", NodeType.AUTH_SERVICE, criticality=95, exposure=40,
                  vulnerabilities=[Vulnerability.WEAK_AUTH]),
        InfraNode("Main Database", NodeType.DATABASE, criticality=100, exposure=20,
                  is_crown_jewel=True, vulnerabilities=[Vulnerability.SQL_INJECTION]),
        InfraNode("Redis Cache", NodeType.CACHE, criticality=60, exposure=30,
                  vulnerabilities=[Vulnerability.NO_ENCRYPTION]),
        InfraNode("Message Queue", NodeType.MESSAGE_QUEUE, criticality=65, exposure=25,
                  vulnerabilities=[Vulnerability.OVERPERMISSIONED]),
        InfraNode("Worker Service", NodeType.WORKER, criticality=50, exposure=15,
                  vulnerabilities=[Vulnerability.DESERIALIZATION]),
        InfraNode("Object Storage", NodeType.STORAGE, criticality=80, exposure=35,
                  vulnerabilities=[Vulnerability.MISCONFIGURATION, Vulnerability.OVERPERMISSIONED]),
        InfraNode("Monitoring", NodeType.MONITORING, criticality=45, exposure=50,
                  vulnerabilities=[Vulnerability.SSRF, Vulnerability.LOG_INJECTION]),
        InfraNode("Third-Party API", NodeType.THIRD_PARTY,
                  criticality=55, exposure=70, is_external=True,
                  vulnerabilities=[Vulnerability.EXPOSED_CREDENTIALS]),
        InfraNode("CDN", NodeType.CDN, criticality=40, exposure=90, is_external=True,
                  vulnerabilities=[Vulnerability.MISCONFIGURATION]),
    ]
    for node in nodes:
        graph.add_node(node)

    edges = [
        InfraEdge("Internet Gateway", "Load Balancer", trust_level=90),
        InfraEdge("Internet Gateway", "CDN", trust_level=70),
        InfraEdge("CDN", "Web API", trust_level=60),
        InfraEdge("Load Balancer", "Web API", trust_level=85),
        InfraEdge("Load Balancer", "Auth Service", trust_level=50),
        InfraEdge("Web API", "Auth Service", trust_level=80),
        InfraEdge("Web API", "Main Database", trust_level=90),
        InfraEdge("Web API", "Redis Cache", trust_level=70),
        InfraEdge("Web API", "Third-Party API", trust_level=60),
        InfraEdge("Web API", "Message Queue", trust_level=65),
        InfraEdge("Message Queue", "Worker Service", trust_level=80),
        InfraEdge("Worker Service", "Main Database", trust_level=75),
        InfraEdge("Worker Service", "Object Storage", trust_level=70),
        InfraEdge("Auth Service", "Main Database", trust_level=85),
        InfraEdge("Monitoring", "Web API", trust_level=40),
        InfraEdge("Monitoring", "Load Balancer", trust_level=30),
    ]
    for edge in edges:
        graph.add_edge(edge)

    return graph
