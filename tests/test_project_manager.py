"""Tests for Project Manager state machine."""

import pytest
import json
from pathlib import Path


class TestProjectState:
    """Test ProjectState dataclass."""

    def test_create_state(self):
        """Test creating a project state."""
        from src.project.state import ProjectState

        state = ProjectState(name="test-project", repo_url="https://github.com/test/repo")

        assert state.name == "test-project"
        assert state.status == "idle"
        assert state.created_at > 0

    def test_valid_transitions(self):
        """Test valid state transitions."""
        from src.project.state import ProjectState

        state = ProjectState(name="test")

        # idle → building
        state.transition_to("building")
        assert state.status == "building"

        # building → testing
        state.transition_to("testing")
        assert state.status == "testing"

        # testing → deployed
        state.transition_to("deployed")
        assert state.status == "deployed"

        # deployed → idle
        state.transition_to("idle")
        assert state.status == "idle"

    def test_invalid_transition(self):
        """Test that invalid transitions raise ValueError."""
        from src.project.state import ProjectState

        state = ProjectState(name="test")
        assert state.status == "idle"

        with pytest.raises(ValueError, match="Invalid transition"):
            state.transition_to("deployed")  # Can't go idle → deployed

    def test_save_and_load(self, tmp_path):
        """Test JSON persistence."""
        from src.project.state import ProjectState

        state = ProjectState(
            name="test-project",
            repo_url="https://github.com/test/repo",
            status="idle",
        )
        state.add_error("Test error")

        state.save(tmp_path)

        loaded = ProjectState.load(tmp_path / "test-project.json")
        assert loaded.name == "test-project"
        assert loaded.repo_url == "https://github.com/test/repo"
        assert len(loaded.error_history) == 1

    def test_error_history_limit(self):
        """Test error history is capped at 50."""
        from src.project.state import ProjectState

        state = ProjectState(name="test")
        for i in range(60):
            state.add_error(f"Error {i}")

        assert len(state.error_history) == 50


class TestProjectManager:
    """Test ProjectManager lifecycle."""

    def _make_config(self, tmp_path):
        """Create a test config."""
        return {
            'projects': {'base_dir': str(tmp_path / 'projects')},
            'logging': {'level': 'DEBUG', 'dir': str(tmp_path / 'logs')},
        }

    def test_create_project(self, tmp_path):
        """Test creating a project."""
        from src.project.manager import ProjectManager

        config = self._make_config(tmp_path)
        pm = ProjectManager(config)

        project = pm.create_project("test-app", "https://github.com/user/test-app")
        assert project.name == "test-app"
        assert pm.project_count == 1

    def test_duplicate_project(self, tmp_path):
        """Test that duplicate names raise ValueError."""
        from src.project.manager import ProjectManager

        config = self._make_config(tmp_path)
        pm = ProjectManager(config)

        pm.create_project("test-app")
        with pytest.raises(ValueError, match="already exists"):
            pm.create_project("test-app")

    def test_list_projects(self, tmp_path):
        """Test listing projects."""
        from src.project.manager import ProjectManager

        config = self._make_config(tmp_path)
        pm = ProjectManager(config)

        pm.create_project("app-1")
        pm.create_project("app-2")

        projects = pm.list_projects()
        assert len(projects) == 2

    def test_status_update(self, tmp_path):
        """Test updating project status."""
        from src.project.manager import ProjectManager

        config = self._make_config(tmp_path)
        pm = ProjectManager(config)

        pm.create_project("test-app")
        pm.update_status("test-app", "building")

        project = pm.get_project("test-app")
        assert project.status == "building"
