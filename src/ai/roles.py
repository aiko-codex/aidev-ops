"""
AI Role definitions for AIDEV-OPS.

Each role maps to a specific model, temperature, and system prompt.
Roles: Planner, Architect, Coder, Reviewer.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIRole:
    """Represents an AI role with its configuration."""
    name: str
    provider: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    system_prompt: str
    extra: dict = field(default_factory=dict)

    def build_messages(self, user_message, context=None):
        """
        Build the messages list for this role.

        Args:
            user_message: The user's prompt/task
            context: Optional additional context to prepend

        Returns:
            list: Messages list for the AI API
        """
        messages = []

        # System message with role prompt
        messages.append({
            "role": "system",
            "content": self.system_prompt.strip()
        })

        # Add context if provided
        if context:
            messages.append({
                "role": "user",
                "content": f"Context:\n{context}"
            })
            messages.append({
                "role": "assistant",
                "content": "I've noted the context. What would you like me to do?"
            })

        # Add the actual task
        messages.append({
            "role": "user",
            "content": user_message
        })

        return messages


def load_roles(config):
    """
    Load AI roles from configuration.

    Args:
        config: Application config dict

    Returns:
        dict: Role name → AIRole instance
    """
    roles_config = config.get('ai', {}).get('roles', {})
    roles = {}

    for role_name, role_conf in roles_config.items():
        roles[role_name] = AIRole(
            name=role_name,
            provider=role_conf.get('provider', 'nvidia'),
            model=role_conf.get('model', ''),
            temperature=role_conf.get('temperature', 0.7),
            top_p=role_conf.get('top_p', 0.8),
            max_tokens=role_conf.get('max_tokens', 4096),
            system_prompt=role_conf.get('system_prompt', ''),
            extra=role_conf.get('extra', {}),
        )

    return roles


# Predefined role descriptions (for documentation/status display)
ROLE_DESCRIPTIONS = {
    "planner": "Task breakdown and planning with reasoning",
    "architect": "System design and technical specification",
    "coder": "Code generation and patch creation",
    "reviewer": "Code validation and security review",
}
