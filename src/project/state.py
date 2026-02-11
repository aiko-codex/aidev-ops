"""
Project state model for AIDEV-OPS.

Dataclass representing a project's current state, persisted as JSON.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from enum import Enum


class ProjectStatus(str, Enum):
    """Valid project states."""
    IDLE = "idle"
    BUILDING = "building"
    TESTING = "testing"
    DEPLOYED = "deployed"
    BLOCKED = "blocked"

    # Valid transitions
    @staticmethod
    def valid_transitions():
        return {
            "idle": ["building"],
            "building": ["testing", "blocked", "idle"],
            "testing": ["deployed", "blocked", "building"],
            "deployed": ["idle", "building"],
            "blocked": ["idle", "building"],
        }


@dataclass
class ProjectState:
    """Represents the state of a managed project."""
    name: str
    repo_url: str = ""
    status: str = "idle"
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    branch: str = "main"
    last_activity: float = 0.0
    created_at: float = 0.0
    error_history: List[str] = field(default_factory=list)
    current_issue: Optional[int] = None
    commit_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.last_activity:
            self.last_activity = time.time()

    def transition_to(self, new_status):
        """
        Transition to a new status if valid.

        Args:
            new_status: Target status string

        Raises:
            ValueError: If transition is not allowed
        """
        valid = ProjectStatus.valid_transitions()
        allowed = valid.get(self.status, [])

        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status} → {new_status}. "
                f"Allowed: {allowed}"
            )

        self.status = new_status
        self.last_activity = time.time()

    def add_error(self, error_msg):
        """Record an error, keeping last 50."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.error_history.append(f"[{timestamp}] {error_msg}")
        if len(self.error_history) > 50:
            self.error_history = self.error_history[-50:]

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items()
                     if k in cls.__dataclass_fields__})

    def save(self, directory):
        """Save state to JSON file."""
        path = Path(directory) / f"{self.name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath):
        """Load state from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
