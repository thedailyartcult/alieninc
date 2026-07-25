"""
CENTRA Plugin Base Class
============================
NASL-modeled plugin architecture for vulnerability checks.
Each plugin defines metadata and an async execute() method.

Plugin types (Nessus-style):
  remote   — No auth required, probes remotely (banners, patches, exploits)
  local    — Authenticates via service (SMB, SSH) to extract information
  combined — Collects information via both remote and local checks
  settings — Defines configuration used by other plugins throughout the scan
  summary  — Summarizes data collected by other plugins (runs AFTER checks)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginResult:
    """Result from a single plugin execution against a target."""
    vulnerable: bool
    target: str
    port: int = 0
    cvss_score: float = 0.0
    severity: str = 'info'
    description: str = ''
    solution: str = ''
    evidence: str = ''
    references: list[str] = field(default_factory=list)


class ScanContext:
    """
    Shared knowledge base (Nessus KB equivalent).
    
    Mirrors Nessus's get_kb_item() / set_kb_item() system. Dependency plugins
    write their findings to named keys. Summary plugins read those keys.
    
    KB Key Convention (Centra namespace):
      Host/scan-start          — ISO timestamp when scan began
      Host/target              — Target host:port
      Services/www             — Service detected on port
    
      bot-template/size         — Bot response size (bytes)
      bot-template/detected     — Bool: template detected?
      bot-human/size            — Human response size (bytes)
      bot-human/visible-data    — Bool: revenue data visible to humans?
      bot-data/blocked          — Bool: data files blocked for bots?
      bot-api/blocked           — Bool: API endpoints blocked for bots?
      bot-paths/blocked         — Bool: sensitive paths return 404?
    
      findings/{plugin_id}/vuln  — Bool: any findings?
      findings/{plugin_id}/sev   — Max severity
      findings/{plugin_id}/detail — Description excerpt
    """
    def __init__(self):
        self._kb: dict[str, object] = {}
        self._plugin_results: dict[int, list[PluginResult]] = {}

    def set_kb_item(self, name: str, value: object):
        self._kb[name] = value

    def get_kb_item(self, name: str) -> object | None:
        return self._kb.get(name)

    def get_kb_list(self, prefix: str) -> dict[str, object]:
        return {k: v for k, v in self._kb.items() if k.startswith(prefix)}

    def add_plugin_results(self, plugin_id: int, results: list[PluginResult]):
        self._plugin_results[plugin_id] = results

    def get_plugin_results(self, plugin_ids: list[int]) -> dict[int, list[PluginResult]]:
        return {pid: self._plugin_results.get(pid, []) for pid in plugin_ids}

    def get_all_results(self) -> dict[int, list[PluginResult]]:
        return dict(self._plugin_results)


class NaslPlugin(ABC):
    """
    Base class for all Centra NASL-style plugins.

    Required class attributes:
        PLUGIN_ID    (int)    — Unique plugin identifier (like Nessus plugin IDs)
        NAME         (str)    — Human-readable plugin name
        FAMILY       (str)    — Plugin family/category
        CVSS_SCORE   (float)  — Base CVSS v3.1 score
        DESCRIPTION  (str)    — What this plugin checks for
        SOLUTION     (str)    — Remediation guidance

    Optional class attributes:
        CVE          (list[str])  — Associated CVE identifiers
        PORTS        (list[int])  — Default ports to check
        FAMILY_WEIGHT (int)       — Priority within family

    Nessus-style type system (NEW):
        PLUGIN_TYPE  (str)    — One of: 'remote', 'local', 'combined',
                                'settings', 'summary'
        DEPENDENCIES (list[int]) — Plugin IDs that must run before this one
        DEPENDENTS   (list[int]) — Plugin IDs that depend on this one
    """
    PLUGIN_ID: int = 0
    NAME: str = 'Unnamed Plugin'
    FAMILY: str = 'General'
    CVSS_SCORE: float = 0.0
    DESCRIPTION: str = ''
    SOLUTION: str = ''
    CVE: list[str] = []
    PORTS: list[int] = []
    FAMILY_WEIGHT: int = 0
    PLUGIN_TYPE: str = 'remote'
    DEPENDENCIES: list[int] = []
    DEPENDENTS: list[int] = []

    @abstractmethod
    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        """
        Execute the vulnerability check against a target.

        Args:
            target: IP address or hostname to scan
            port: Specific port to check (optional, plugin may check multiple)
            scan_context: Shared context with results from other plugins
                          (populated for summary plugins, None for remote/local)

        Returns:
            List of PluginResult objects (can be empty if no vulnerability found)
        """
        pass

    async def run(self, target: str, port: int | None = None,
                  scan_context: ScanContext | None = None) -> list[PluginResult]:
        """Safe wrapper around check_target with error handling."""
        try:
            if self.PLUGIN_TYPE == 'summary':
                result = await self.check_target(target, port, scan_context)
            else:
                result = await self.check_target(target, port)
            if isinstance(result, PluginResult):
                return [result]
            return result or []
        except Exception as e:
            return [PluginResult(
                vulnerable=False,
                target=target,
                description=f'Plugin error: {str(e)}',
                severity='info'
            )]

    def severity_from_cvss(self, score: float) -> str:
        if score >= 9.0: return 'critical'
        if score >= 7.0: return 'high'
        if score >= 4.0: return 'medium'
        if score > 0.0: return 'low'
        return 'info'

    def to_dict(self) -> dict:
        return {
            'id': self.PLUGIN_ID,
            'name': self.NAME,
            'family': self.FAMILY,
            'type': self.PLUGIN_TYPE,
            'cvss': self.CVSS_SCORE,
            'cve': self.CVE,
            'dependencies': self.DEPENDENCIES,
            'description': self.DESCRIPTION,
            'solution': self.SOLUTION,
        }
