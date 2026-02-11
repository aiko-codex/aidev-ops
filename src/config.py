"""
Configuration loader for AIDEV-OPS.

Reads config.yaml and .env, resolves ${VAR} placeholders,
and provides a typed configuration dictionary.
"""

import os
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv


# Default config location relative to project root
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_ENV_PATH = ".env"


def _resolve_env_vars(value):
    """Recursively resolve ${VAR} placeholders in config values."""
    if isinstance(value, str):
        pattern = re.compile(r'\$\{(\w+)\}')
        def replacer(match):
            env_var = match.group(1)
            env_val = os.environ.get(env_var, "")
            if not env_val:
                print(f"  [WARN] Environment variable {env_var} is not set")
            return env_val
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def _find_project_root():
    """Find the project root by looking for config.yaml."""
    # Check current directory first
    cwd = Path.cwd()
    if (cwd / DEFAULT_CONFIG_PATH).exists():
        return cwd

    # Check the directory of this file
    src_dir = Path(__file__).parent
    project_dir = src_dir.parent
    if (project_dir / DEFAULT_CONFIG_PATH).exists():
        return project_dir

    # Fallback to /opt/aidev
    opt_dir = Path("/opt/aidev")
    if (opt_dir / DEFAULT_CONFIG_PATH).exists():
        return opt_dir

    raise FileNotFoundError(
        f"Cannot find {DEFAULT_CONFIG_PATH} in any expected location. "
        f"Searched: {cwd}, {project_dir}, {opt_dir}"
    )


def load_config(config_path=None, env_path=None):
    """
    Load and return the resolved configuration dictionary.

    Args:
        config_path: Path to config.yaml (auto-detected if None)
        env_path: Path to .env file (auto-detected if None)

    Returns:
        dict: Fully resolved configuration
    """
    # Find project root
    project_root = _find_project_root()

    # Load .env file
    env_file = Path(env_path) if env_path else project_root / DEFAULT_ENV_PATH
    if env_file.exists():
        load_dotenv(env_file, override=True)
    else:
        print(f"  [WARN] No .env file found at {env_file}")

    # Load config.yaml
    config_file = Path(config_path) if config_path else project_root / DEFAULT_CONFIG_PATH
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file, 'r') as f:
        raw_config = yaml.safe_load(f)

    # Resolve environment variable placeholders
    config = _resolve_env_vars(raw_config)

    # Inject project root
    config['_project_root'] = str(project_root)

    # Validate required fields
    _validate_config(config)

    return config


def _validate_config(config):
    """Validate that critical configuration fields are present."""
    errors = []

    # Check AI provider keys
    ai_config = config.get('ai', {})
    providers = ai_config.get('providers', {})
    nvidia = providers.get('nvidia', {})
    api_keys = nvidia.get('api_keys', [])

    valid_keys = [k for k in api_keys if k and not k.startswith('nvapi-your')]
    if not valid_keys:
        errors.append("No valid NVIDIA API keys configured. Update .env file.")

    # Check roles
    roles = ai_config.get('roles', {})
    required_roles = ['planner', 'architect', 'coder', 'reviewer']
    for role in required_roles:
        if role not in roles:
            errors.append(f"Missing AI role configuration: {role}")

    if errors:
        print("  [CONFIG WARNINGS]")
        for err in errors:
            print(f"    ⚠ {err}")

    return len(errors) == 0


def get_data_dir(config):
    """Get the data directory path, creating it if needed."""
    data_dir = Path(config.get('server', {}).get('data_dir', '/opt/aidev'))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir(config):
    """Get the logging directory path, creating it if needed."""
    log_dir = Path(config.get('logging', {}).get('dir', '/opt/aidev/logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_projects_dir(config):
    """Get the projects directory path, creating it if needed."""
    projects_dir = Path(config.get('projects', {}).get('base_dir', '/opt/aidev/projects'))
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir
