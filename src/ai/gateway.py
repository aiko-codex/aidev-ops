"""
Unified AI Gateway for AIDEV-OPS.

Routes requests to NVIDIA API via OpenAI-compatible provider.
Manages 2 API keys with round-robin rotation and automatic
failover on 429/quota errors. Tracks per-key usage.
"""

import time
from openai import RateLimitError, APIError
from src.ai.providers import NvidiaProvider
from src.ai.roles import load_roles
from src.logger import setup_logger


class AIGateway:
    """
    Central AI gateway that manages providers, keys, and role-based routing.

    Features:
    - Round-robin key rotation across requests
    - Automatic failover when a key hits rate limits
    - Role-based model selection (Planner → Kimi, Coder → Qwen3-Coder, etc.)
    - Request/error tracking per key
    - Cooldown period for rate-limited keys
    """

    # Cooldown period after a rate limit error (seconds)
    RATE_LIMIT_COOLDOWN = 60

    def __init__(self, config):
        """
        Initialize the AI Gateway.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('ai_gateway', config)
        self.roles = load_roles(config)

        # Initialize providers (one per API key)
        self._providers = []
        self._current_provider_idx = 0
        self._key_cooldowns = {}  # key_index → cooldown_until timestamp

        self._init_providers()

    def _init_providers(self):
        """Initialize NVIDIA providers for each API key."""
        ai_config = self.config.get('ai', {})
        nvidia_config = ai_config.get('providers', {}).get('nvidia', {})

        base_url = nvidia_config.get('base_url', 'https://integrate.api.nvidia.com/v1')
        api_keys = nvidia_config.get('api_keys', [])

        if not api_keys:
            self.logger.error("No API keys configured!")
            return

        for i, key in enumerate(api_keys):
            if key and not key.startswith('nvapi-your'):
                provider = NvidiaProvider(base_url, key, self.config)
                self._providers.append(provider)
                self.logger.info(
                    f"Initialized NVIDIA provider #{i+1} "
                    f"(key: ...{key[-8:]})"
                )

        if not self._providers:
            self.logger.error("No valid API keys found! Check .env file.")

        self.logger.info(
            f"AI Gateway ready with {len(self._providers)} provider(s), "
            f"strategy: {nvidia_config.get('key_strategy', 'round-robin')}"
        )

    def _get_next_provider(self):
        """
        Get the next available provider using round-robin with cooldown check.

        Returns:
            NvidiaProvider instance or None if all are on cooldown
        """
        if not self._providers:
            raise RuntimeError("No AI providers available")

        now = time.time()
        attempts = len(self._providers)

        for _ in range(attempts):
            idx = self._current_provider_idx % len(self._providers)
            cooldown_until = self._key_cooldowns.get(idx, 0)

            if now >= cooldown_until:
                self._current_provider_idx = idx + 1
                return self._providers[idx], idx

            self._current_provider_idx += 1

        # All keys on cooldown — use the one with shortest remaining cooldown
        min_idx = min(self._key_cooldowns, key=self._key_cooldowns.get)
        wait_time = self._key_cooldowns[min_idx] - now
        self.logger.warning(
            f"All API keys on cooldown. Shortest wait: {wait_time:.0f}s"
        )
        time.sleep(max(wait_time, 1))
        return self._providers[min_idx], min_idx

    def chat(self, role_name, user_message, context=None, stream=False):
        """
        Send a chat request using the specified AI role.

        Args:
            role_name: Role to use ('planner', 'architect', 'coder', 'reviewer')
            user_message: The task/prompt to send
            context: Optional context string
            stream: Whether to stream the response

        Returns:
            str: AI response text

        Raises:
            ValueError: If role is unknown
            RuntimeError: If all providers fail
        """
        if role_name not in self.roles:
            raise ValueError(
                f"Unknown role '{role_name}'. "
                f"Available: {list(self.roles.keys())}"
            )

        role = self.roles[role_name]
        messages = role.build_messages(user_message, context)

        self.logger.info(
            f"[{role_name.upper()}] Sending request "
            f"(model: {role.model}, tokens: {role.max_tokens})"
        )

        # Try each provider with failover
        last_error = None
        for attempt in range(len(self._providers)):
            provider, idx = self._get_next_provider()

            try:
                response = provider.chat(
                    model=role.model,
                    messages=messages,
                    temperature=role.temperature,
                    top_p=role.top_p,
                    max_tokens=role.max_tokens,
                    stream=stream,
                    extra_params=role.extra if role.extra else None,
                )

                if stream:
                    self.logger.info(
                        f"[{role_name.upper()}] Streaming response started via key #{idx+1}"
                    )
                else:
                    self.logger.info(
                        f"[{role_name.upper()}] Response received "
                        f"({len(response)} chars) via key #{idx+1}"
                    )
                return response

            except RateLimitError as e:
                self.logger.warning(
                    f"[{role_name.upper()}] Rate limit on key #{idx+1}, "
                    f"cooling down {self.RATE_LIMIT_COOLDOWN}s"
                )
                self._key_cooldowns[idx] = time.time() + self.RATE_LIMIT_COOLDOWN
                last_error = e
                continue

            except APIError as e:
                self.logger.error(
                    f"[{role_name.upper()}] API error on key #{idx+1}: {e}"
                )
                last_error = e
                continue

            except Exception as e:
                self.logger.error(
                    f"[{role_name.upper()}] Unexpected error: {e}"
                )
                last_error = e
                continue

        raise RuntimeError(
            f"All providers failed for role '{role_name}'. "
            f"Last error: {last_error}"
        )

    def plan(self, task, context=None):
        """Convenience: Use Planner role."""
        return self.chat('planner', task, context)

    def design(self, task, context=None):
        """Convenience: Use Architect role."""
        return self.chat('architect', task, context)

    def code(self, task, context=None):
        """Convenience: Use Coder role."""
        return self.chat('coder', task, context)

    def review(self, code, context=None):
        """Convenience: Use Reviewer role."""
        return self.chat('reviewer', code, context)

    def health_check(self):
        """Check health of all providers."""
        results = {}
        for i, provider in enumerate(self._providers):
            results[f"provider_{i+1}"] = provider.health_check()
        return results

    @property
    def stats(self):
        """Get stats for all providers."""
        return {
            "total_providers": len(self._providers),
            "current_index": self._current_provider_idx % max(len(self._providers), 1),
            "providers": [p.stats for p in self._providers],
            "cooldowns": {
                k: max(0, v - time.time())
                for k, v in self._key_cooldowns.items()
            },
        }

    @property
    def available_roles(self):
        """List available AI roles."""
        return {
            name: {
                "model": role.model,
                "provider": role.provider,
            }
            for name, role in self.roles.items()
        }
