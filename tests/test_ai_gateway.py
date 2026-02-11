"""Tests for AI Gateway routing and failover."""

import pytest
from unittest.mock import MagicMock, patch


class TestAIRoles:
    """Test AI role definitions."""

    def test_load_roles(self):
        """Test loading roles from config."""
        from src.ai.roles import load_roles

        config = {
            'ai': {
                'roles': {
                    'planner': {
                        'provider': 'nvidia',
                        'model': 'moonshotai/kimi-k2.5',
                        'temperature': 1.0,
                        'top_p': 1.0,
                        'max_tokens': 16384,
                        'system_prompt': 'You are a planner.',
                    },
                    'coder': {
                        'provider': 'nvidia',
                        'model': 'qwen/qwen3-coder-480b-a35b-instruct',
                        'temperature': 0.7,
                        'top_p': 0.8,
                        'max_tokens': 4096,
                        'system_prompt': 'You are a coder.',
                    },
                }
            }
        }

        roles = load_roles(config)
        assert 'planner' in roles
        assert 'coder' in roles
        assert roles['planner'].model == 'moonshotai/kimi-k2.5'
        assert roles['coder'].temperature == 0.7

    def test_build_messages(self):
        """Test message building for a role."""
        from src.ai.roles import AIRole

        role = AIRole(
            name='reviewer',
            provider='nvidia',
            model='test',
            temperature=0.5,
            top_p=0.8,
            max_tokens=100,
            system_prompt='Review code carefully.',
        )

        messages = role.build_messages("Check this code")
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[1]['role'] == 'user'
        assert 'Review code' in messages[0]['content']

    def test_build_messages_with_context(self):
        """Test message building with context."""
        from src.ai.roles import AIRole

        role = AIRole(
            name='coder',
            provider='nvidia',
            model='test',
            temperature=0.7,
            top_p=0.8,
            max_tokens=100,
            system_prompt='Write code.',
        )

        messages = role.build_messages("Fix the bug", context="File: app.php")
        assert len(messages) == 4  # system + context + ack + task
        assert 'File: app.php' in messages[1]['content']


class TestAIGateway:
    """Test AI Gateway routing."""

    def _make_config(self):
        """Create a test config."""
        return {
            'ai': {
                'providers': {
                    'nvidia': {
                        'base_url': 'https://integrate.api.nvidia.com/v1',
                        'api_keys': ['nvapi-test-key-1', 'nvapi-test-key-2'],
                        'key_strategy': 'round-robin',
                    }
                },
                'roles': {
                    'reviewer': {
                        'provider': 'nvidia',
                        'model': 'qwen/qwen3-next-80b-a3b-instruct',
                        'temperature': 0.6,
                        'top_p': 0.7,
                        'max_tokens': 4096,
                        'system_prompt': 'Review code.',
                    },
                },
            },
            'logging': {'level': 'DEBUG', 'dir': './test_logs'},
        }

    def test_gateway_init(self):
        """Test gateway initializes with providers."""
        from src.ai.gateway import AIGateway

        config = self._make_config()
        gateway = AIGateway(config)

        assert len(gateway._providers) == 2
        assert 'reviewer' in gateway.roles

    def test_unknown_role_raises(self):
        """Test that unknown role raises ValueError."""
        from src.ai.gateway import AIGateway

        config = self._make_config()
        gateway = AIGateway(config)

        with pytest.raises(ValueError, match="Unknown role"):
            gateway.chat('nonexistent', 'hello')

    def test_available_roles(self):
        """Test listing available roles."""
        from src.ai.gateway import AIGateway

        config = self._make_config()
        gateway = AIGateway(config)

        roles = gateway.available_roles
        assert 'reviewer' in roles
        assert roles['reviewer']['model'] == 'qwen/qwen3-next-80b-a3b-instruct'
