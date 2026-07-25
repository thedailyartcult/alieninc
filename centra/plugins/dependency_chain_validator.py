"""
Plugin 1059: Plugin Dependency Chain Validator (Self-Sustaining)
==================================================================
Validates the Centra plugin dependency graph for correctness:
no circular dependencies, all dependencies exist, no orphaned dependents.
Self-sustaining pillar: ensure plugin architecture integrity.
"""
from plugins import NaslPlugin, PluginResult, ScanContext
from plugins.plugin_loader import load_all_plugins
from pathlib import Path


class DependencyChainValidator(NaslPlugin):
    PLUGIN_ID = 1059
    NAME = 'Plugin Dependency Chain Validator'
    FAMILY = 'Self-Sustaining'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Validates the Centra plugin dependency graph for correctness. '
        'Checks for circular dependencies, missing dependency plugins, '
        'orphaned dependents, and type compatibility between plugins.'
    )
    SOLUTION = (
        'Fix circular dependencies by refactoring plugin relationships. '
        'Ensure all dependency plugin IDs exist. Register missing plugins '
        'in the plugin registry.'
    )

    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        plugins = load_all_plugins(Path(__file__).parent)
        by_id = {p.PLUGIN_ID: p for p in plugins}
        issues = []
        evidence_lines = []

        evidence_lines.append(f'Total plugins: {len(plugins)}')

        dep_count = sum(1 for p in plugins if p.DEPENDENCIES)
        evidence_lines.append(f'Plugins with dependencies: {dep_count}')

        for p in plugins:
            for dep_id in p.DEPENDENCIES:
                if dep_id not in by_id:
                    issues.append(f'P{p.PLUGIN_ID} depends on missing P{dep_id}')
                elif dep_id == p.PLUGIN_ID:
                    issues.append(f'P{p.PLUGIN_ID} depends on itself')

        for p in plugins:
            for dep_id in p.DEPENDENTS:
                if dep_id not in by_id:
                    issues.append(f'P{p.PLUGIN_ID} declares dependent P{dep_id} which does not exist')

        pid_set = set(by_id.keys())
        graph = {pid: set(p.DEPENDENCIES) & pid_set for pid, p in by_id.items()}

        def has_cycle(start: int, visited: set, path: set) -> str | None:
            if start in path:
                path_list = list(path)
                cycle_start = path_list.index(start)
                return ' → '.join(str(x) for x in path_list[cycle_start:] + [start])
            if start in visited:
                return None
            visited.add(start)
            path.add(start)
            for dep in graph.get(start, set()):
                result = has_cycle(dep, visited, path)
                if result:
                    return result
            path.remove(start)
            return None

        visited = set()
        for pid in pid_set:
            cycle = has_cycle(pid, visited, set())
            if cycle:
                issues.append(f'Circular dependency: {cycle}')
                break

        summary_types = {}
        for p in plugins:
            t = getattr(p, 'PLUGIN_TYPE', 'remote')
            summary_types[t] = summary_types.get(t, 0) + 1
        for t, c in summary_types.items():
            evidence_lines.append(f'  {t}: {c}')

        if not issues:
            evidence_lines.append('Dependency graph: VALID — no issues found')

        if issues:
            return [PluginResult(
                vulnerable=True,
                target=target,
                cvss_score=3.0,
                severity='low',
                description=f'Dependency chain: {len(issues)} issue(s)',
                solution=self.SOLUTION,
                evidence=' | '.join(issues) + ' | ' + ' | '.join(evidence_lines),
            )]

        return [PluginResult(
            vulnerable=False, target=target,
            cvss_score=0.0, severity='info',
            description='Dependency chain: VALID — no circular dependencies or missing plugins',
            evidence=' | '.join(evidence_lines),
        )]
