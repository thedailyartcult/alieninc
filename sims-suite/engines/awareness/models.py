"""Awareness data models — threats, playbooks, and incident responses.

A ``ThreatEvent`` is an incoming intelligence signal (could come from GDELT
geopolitical events, Citadel predicted infrastructure breaks, or synthetic
adversary simulation). For each threat, the engine generates ``Playbook``
objects — structured response sequences. Each playbook is then branched
through Monte Carlo to measure containment time, damage mitigated, and
operational continuity preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ThreatType(str, Enum):
    """Categories of threats the IR layer responds to."""

    DATA_BREACH = "data_breach"
    RANSOMWARE = "ransomware"
    SUPPLY_CHAIN_ATTACK = "supply_chain_attack"
    DDoS = "ddos"
    INSIDER_THREAT = "insider_threat"
    ZERO_DAY = "zero_day"
    CREDENTIAL_THEFT = "credential_theft"
    LATERAL_MOVEMENT = "lateral_movement"
    GEOPOLITICAL_EVENT = "geopolitical_event"
    INFRA_FAILURE = "infra_failure"
    PHISHING_CAMPAIGN = "phishing_campaign"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class ThreatSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResponseAction(str, Enum):
    """Atomic actions a playbook can execute."""

    ISOLATE_HOST = "isolate_host"
    BLOCK_IP = "block_ip"
    ROTATE_CREDENTIALS = "rotate_credentials"
    PATCH_SYSTEM = "patch_system"
    DISABLE_ACCOUNT = "disable_account"
    INCREASE_MONITORING = "increase_monitoring"
    FAILOVER_SERVICE = "failover_service"
    NOTIFY_STAKEHOLDERS = "notify_stakeholders"
    DEPLOY_DECOY = "deploy_decoy"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    QUARANTINE_EMAIL = "quarantine_email"
    UPDATE_FIREWALL = "update_firewall"
    CAPTURE_FORENSICS = "capture_forensics"
    SHUTDOWN_SERVICE = "shutdown_service"
    ENGAGE_IR_TEAM = "engage_ir_team"


class ResponseOutcome(str, Enum):
    CONTAINED = "contained"
    PARTIALLY_CONTAINED = "partially_contained"
    FAILED = "failed"
    EXACERBATED = "exacerbated"


@dataclass
class ThreatEvent:
    """An incoming threat that requires a response."""

    name: str
    threat_type: ThreatType
    severity: ThreatSeverity
    affected_assets: list[str] = field(default_factory=list)
    detection_confidence: float = 80.0      # 0-100
    spread_rate: float = 50.0               # 0-100, how fast it propagates
    persistence: float = 50.0               # 0-100, how hard to eradicate
    origin: str = "external"                # "external", "internal", "supply_chain", "gdelt"

    @property
    def urgency_score(self) -> float:
        """How urgently this threat needs response (0-100)."""
        severity_weight = {"low": 20, "medium": 40, "high": 70, "critical": 95}
        return (severity_weight.get(self.severity.value, 50)
                + self.spread_rate * 0.3
                + self.detection_confidence * 0.2)


@dataclass
class Playbook:
    """A structured response sequence for a threat."""

    name: str
    actions: list[ResponseAction]
    target_threat_type: ThreatType
    speed: float = 50.0                     # 0-100, how fast the playbook executes
    coverage: float = 50.0                  # 0-100, how much of the threat it addresses
    collateral_risk: float = 20.0           # 0-100, risk of disrupting legitimate operations
    automation_level: float = 50.0          # 0-100, how much runs without human intervention

    @property
    def effectiveness(self) -> float:
        """Base effectiveness before stochastic variation."""
        return (self.coverage * 0.40 + self.speed * 0.30
                + self.automation_level * 0.15
                + (100 - self.collateral_risk) * 0.15)


@dataclass
class IncidentResponse:
    """The result of one branched response scenario."""

    playbook_name: str
    threat_name: str
    outcome: ResponseOutcome
    containment_time_min: float             # minutes to contain
    damage_mitigated_pct: float             # 0-100, how much damage was prevented
    collateral_damage_pct: float            # 0-100, disruption to legitimate ops
    operational_continuity: float           # 0-100, how much service was preserved
    actions_executed: int                   # how many actions completed
    score: float = 0.0                      # for best_branch()
    outcome_label: str = ""                 # for convergence_rate()


# --- Predefined threat scenarios ---

SAMPLE_THREATS: list[ThreatEvent] = [
    ThreatEvent("Ransomware Outbreak", ThreatType.RANSOMWARE, ThreatSeverity.CRITICAL,
                affected_assets=["File Servers", "Workstations", "Backup Systems"],
                detection_confidence=85, spread_rate=90, persistence=80, origin="external"),
    ThreatEvent("Supply Chain Compromise", ThreatType.SUPPLY_CHAIN_ATTACK, ThreatSeverity.CRITICAL,
                affected_assets=["CI/CD Pipeline", "Build Servers", "Third-Party Libraries"],
                detection_confidence=60, spread_rate=70, persistence=90, origin="supply_chain"),
    ThreatEvent("Credential Phishing Wave", ThreatType.PHISHING_CAMPAIGN, ThreatSeverity.HIGH,
                affected_assets=["Email System", "User Accounts", "OAuth Tokens"],
                detection_confidence=90, spread_rate=60, persistence=40, origin="external"),
    ThreatEvent("Zero-Day Exploitation", ThreatType.ZERO_DAY, ThreatSeverity.CRITICAL,
                affected_assets=["Web API", "Auth Service"],
                detection_confidence=40, spread_rate=85, persistence=95, origin="external"),
    ThreatEvent("Insider Data Exfiltration", ThreatType.INSIDER_THREAT, ThreatSeverity.HIGH,
                affected_assets=["Customer Database", "Cloud Storage"],
                detection_confidence=55, spread_rate=30, persistence=70, origin="internal"),
    ThreatEvent("DDoS Against Edge", ThreatType.DDoS, ThreatSeverity.HIGH,
                affected_assets=["Load Balancer", "CDN", "DNS"],
                detection_confidence=95, spread_rate=100, persistence=20, origin="external"),
    ThreatEvent("Lateral Movement Detected", ThreatType.LATERAL_MOVEMENT, ThreatSeverity.HIGH,
                affected_assets=["Workstations", "Domain Controller", "File Shares"],
                detection_confidence=70, spread_rate=75, persistence=60, origin="external"),
    ThreatEvent("Geopolitical: Regional Conflict", ThreatType.GEOPOLITICAL_EVENT, ThreatSeverity.HIGH,
                affected_assets=["Regional Data Center", "Local Staff", "Supply Routes"],
                detection_confidence=80, spread_rate=50, persistence=85, origin="gdelt"),
]


# --- Predefined playbooks ---

SAMPLE_PLAYBOOKS: list[Playbook] = [
    Playbook("Rapid Isolation", [
        ResponseAction.ISOLATE_HOST, ResponseAction.BLOCK_IP,
        ResponseAction.ENGAGE_IR_TEAM, ResponseAction.CAPTURE_FORENSICS,
    ], ThreatType.RANSOMWARE, speed=85, coverage=75, collateral_risk=35, automation_level=80),
    Playbook("Credential Sweep", [
        ResponseAction.ROTATE_CREDENTIALS, ResponseAction.DISABLE_ACCOUNT,
        ResponseAction.UPDATE_FIREWALL, ResponseAction.NOTIFY_STAKEHOLDERS,
    ], ThreatType.CREDENTIAL_THEFT, speed=70, coverage=85, collateral_risk=15, automation_level=65),
    Playbook("Contain & Patch", [
        ResponseAction.PATCH_SYSTEM, ResponseAction.ISOLATE_HOST,
        ResponseAction.INCREASE_MONITORING, ResponseAction.ENGAGE_IR_TEAM,
    ], ThreatType.ZERO_DAY, speed=50, coverage=80, collateral_risk=25, automation_level=45),
    Playbook("Failover & Restore", [
        ResponseAction.FAILOVER_SERVICE, ResponseAction.ROLLBACK_DEPLOYMENT,
        ResponseAction.NOTIFY_STAKEHOLDERS, ResponseAction.CAPTURE_FORENSICS,
    ], ThreatType.INFRA_FAILURE, speed=75, coverage=70, collateral_risk=40, automation_level=85),
    Playbook("Email Quarantine", [
        ResponseAction.QUARANTINE_EMAIL, ResponseAction.DISABLE_ACCOUNT,
        ResponseAction.NOTIFY_STAKEHOLDERS, ResponseAction.INCREASE_MONITORING,
    ], ThreatType.PHISHING_CAMPAIGN, speed=90, coverage=80, collateral_risk=10, automation_level=90),
    Playbook("DDoS Mitigation", [
        ResponseAction.BLOCK_IP, ResponseAction.UPDATE_FIREWALL,
        ResponseAction.FAILOVER_SERVICE, ResponseAction.INCREASE_MONITORING,
    ], ThreatType.DDoS, speed=95, coverage=85, collateral_risk=20, automation_level=95),
    Playbook("Threat Hunt & Eradicate", [
        ResponseAction.ENGAGE_IR_TEAM, ResponseAction.CAPTURE_FORENSICS,
        ResponseAction.ISOLATE_HOST, ResponseAction.PATCH_SYSTEM,
        ResponseAction.ROTATE_CREDENTIALS, ResponseAction.INCREASE_MONITORING,
    ], ThreatType.LATERAL_MOVEMENT, speed=40, coverage=90, collateral_risk=30, automation_level=35),
    Playbook("Decoy & Observe", [
        ResponseAction.DEPLOY_DECOY, ResponseAction.INCREASE_MONITORING,
        ResponseAction.CAPTURE_FORENSICS, ResponseAction.NOTIFY_STAKEHOLDERS,
    ], ThreatType.INSIDER_THREAT, speed=30, coverage=65, collateral_risk=5, automation_level=50),
    Playbook("Supply Chain Freeze", [
        ResponseAction.SHUTDOWN_SERVICE, ResponseAction.ROLLBACK_DEPLOYMENT,
        ResponseAction.ROTATE_CREDENTIALS, ResponseAction.ENGAGE_IR_TEAM,
        ResponseAction.CAPTURE_FORENSICS,
    ], ThreatType.SUPPLY_CHAIN_ATTACK, speed=60, coverage=85, collateral_risk=55, automation_level=40),
    Playbook("Geopolitical Evacuation", [
        ResponseAction.FAILOVER_SERVICE, ResponseAction.NOTIFY_STAKEHOLDERS,
        ResponseAction.ROTATE_CREDENTIALS, ResponseAction.UPDATE_FIREWALL,
    ], ThreatType.GEOPOLITICAL_EVENT, speed=65, coverage=60, collateral_risk=45, automation_level=55),
]
