# Finance Module — Portfolio, Market, Metrics, Optimizer, Risk
# Lazy attribute resolution (PEP 562) keeps submodule imports cycle-free.

import importlib

__all__ = [
    "STRATEGIES",
    "PortfolioEngine",
    "MarketSimulator",
    "MarketYear",
    "compute_alpha",
    "compute_beta",
    "compute_convergence",
    "compute_max_drawdown",
    "compute_metrics",
    "compute_sharpe_ratio",
    "AllocationOption",
    "PortfolioOptimizer",
    "RiskAnalyzer",
]

_MODULE_MAP = {
    "STRATEGIES": "finance.portfolio",
    "PortfolioEngine": "finance.portfolio",
    "MarketSimulator": "finance.market",
    "MarketYear": "finance.market",
    "compute_alpha": "finance.metrics",
    "compute_beta": "finance.metrics",
    "compute_convergence": "finance.metrics",
    "compute_max_drawdown": "finance.metrics",
    "compute_metrics": "finance.metrics",
    "compute_sharpe_ratio": "finance.metrics",
    "AllocationOption": "finance.optimizer",
    "PortfolioOptimizer": "finance.optimizer",
    "RiskAnalyzer": "finance.risk",
}


def __getattr__(name: str):
    module_name = _MODULE_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module 'finance' has no attribute {name!r}")
    module = importlib.import_module(module_name)
    return getattr(module, name)
