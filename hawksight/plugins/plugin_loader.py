"""Dynamic plugin loader — discovers and instantiates all NASL-style plugins."""
import importlib
import importlib.util
import sys
import logging
from pathlib import Path

logger = logging.getLogger('hawksight.plugins')


def load_all_plugins(plugins_dir: Path) -> list:
    """Load all plugin classes from the plugins directory."""
    plugins = []
    plugins_dir = Path(plugins_dir).resolve()

    # Ensure the parent directory is in sys.path so 'plugins' is importable as a package
    parent_dir = str(plugins_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # First, load the base class from __init__.py
    init_file = plugins_dir / '__init__.py'
    if init_file.exists():
        spec = importlib.util.spec_from_file_location(
            'plugins', str(init_file),
            submodule_search_locations=[str(plugins_dir)]
        )
        pkg = importlib.util.module_from_spec(spec)
        sys.modules['plugins'] = pkg
        spec.loader.exec_module(pkg)

    # Now load each plugin module
    for py_file in sorted(plugins_dir.glob('*.py')):
        if py_file.name.startswith('_') or py_file.name == 'plugin_loader.py':
            continue

        module_name = f'plugins.{py_file.stem}'
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, str(py_file)
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and hasattr(attr, 'PLUGIN_ID')
                        and attr.PLUGIN_ID > 0
                        and attr_name != 'NaslPlugin'):
                    instance = attr()
                    plugins.append(instance)
                    logger.info(f'Loaded plugin: {instance.PLUGIN_ID} — {instance.NAME}')

        except Exception as e:
            logger.error(f'Failed to load plugin {py_file.name}: {e}')

    plugins.sort(key=lambda p: p.PLUGIN_ID)
    return plugins
