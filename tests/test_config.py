"""Tests for configuration loading."""

import os
import pytest
import tempfile
import yaml
from pathlib import Path


class TestConfigLoader:
    """Test the configuration system."""

    def _create_test_config(self, tmpdir, config_data=None, env_data=None):
        """Helper to create config files in temp directory."""
        if config_data is None:
            config_data = {
                'server': {'mode': 'test', 'port': 9000},
                'ai': {
                    'providers': {
                        'nvidia': {
                            'base_url': 'https://integrate.api.nvidia.com/v1',
                            'api_keys': ['${NVIDIA_API_KEY_1}', '${NVIDIA_API_KEY_2}'],
                        }
                    },
                    'roles': {
                        'planner': {'provider': 'nvidia', 'model': 'test-model',
                                    'temperature': 0.7, 'top_p': 0.8,
                                    'max_tokens': 100, 'system_prompt': 'test'},
                        'architect': {'provider': 'nvidia', 'model': 'test-model',
                                      'temperature': 0.7, 'top_p': 0.8,
                                      'max_tokens': 100, 'system_prompt': 'test'},
                        'coder': {'provider': 'nvidia', 'model': 'test-model',
                                  'temperature': 0.7, 'top_p': 0.8,
                                  'max_tokens': 100, 'system_prompt': 'test'},
                        'reviewer': {'provider': 'nvidia', 'model': 'test-model',
                                     'temperature': 0.7, 'top_p': 0.8,
                                     'max_tokens': 100, 'system_prompt': 'test'},
                    },
                },
                'docker': {'memory_limit': '512m'},
                'logging': {'level': 'DEBUG', 'dir': str(tmpdir / 'logs')},
                'projects': {'base_dir': str(tmpdir / 'projects')},
            }

        config_path = tmpdir / 'config.yaml'
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        env_path = tmpdir / '.env'
        if env_data:
            with open(env_path, 'w') as f:
                for k, v in env_data.items():
                    f.write(f"{k}={v}\n")

        return str(config_path), str(env_path)

    def test_load_config_basic(self, tmp_path):
        """Test basic config loading."""
        from src.config import load_config

        config_path, env_path = self._create_test_config(
            tmp_path,
            env_data={
                'NVIDIA_API_KEY_1': 'nvapi-test-key-1',
                'NVIDIA_API_KEY_2': 'nvapi-test-key-2',
            }
        )

        config = load_config(config_path, env_path)

        assert config['server']['mode'] == 'test'
        assert config['server']['port'] == 9000

    def test_env_var_resolution(self, tmp_path):
        """Test that ${VAR} placeholders are resolved from .env."""
        from src.config import load_config

        config_path, env_path = self._create_test_config(
            tmp_path,
            env_data={
                'NVIDIA_API_KEY_1': 'nvapi-resolved-key-1',
                'NVIDIA_API_KEY_2': 'nvapi-resolved-key-2',
            }
        )

        config = load_config(config_path, env_path)
        keys = config['ai']['providers']['nvidia']['api_keys']

        assert keys[0] == 'nvapi-resolved-key-1'
        assert keys[1] == 'nvapi-resolved-key-2'

    def test_missing_config_file(self):
        """Test error when config file doesn't exist."""
        from src.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config('/nonexistent/config.yaml')

    def test_roles_loaded(self, tmp_path):
        """Test that all 4 roles are loaded."""
        from src.config import load_config

        config_path, env_path = self._create_test_config(tmp_path)
        config = load_config(config_path, env_path)

        roles = config['ai']['roles']
        assert 'planner' in roles
        assert 'architect' in roles
        assert 'coder' in roles
        assert 'reviewer' in roles
