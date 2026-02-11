"""
Project Manager for AIDEV-OPS.

Handles project lifecycle: create, list, status transitions,
and directory management. Projects are stored under the configured
base_dir with state persisted as JSON.
"""

import time
from pathlib import Path
from src.project.state import ProjectState, ProjectStatus
from src.config import get_projects_dir
from src.logger import setup_logger


class ProjectManager:
    """
    Manages the lifecycle of development projects.

    Each project has:
    - An isolated directory under projects_dir/
    - A JSON state file tracking status, container, errors
    - A state machine governing transitions
    """

    def __init__(self, config):
        """
        Initialize the Project Manager.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('project_manager', config)
        self.projects_dir = get_projects_dir(config)
        self.states_dir = self.projects_dir / ".states"
        self.states_dir.mkdir(parents=True, exist_ok=True)

        # Cache loaded projects
        self._projects = {}
        self._load_existing_projects()

    def _load_existing_projects(self):
        """Load all existing project states from disk."""
        for state_file in self.states_dir.glob("*.json"):
            try:
                project = ProjectState.load(state_file)
                self._projects[project.name] = project
                self.logger.debug(f"Loaded project: {project.name} [{project.status}]")
            except Exception as e:
                self.logger.error(f"Failed to load state {state_file}: {e}")

        self.logger.info(f"Loaded {len(self._projects)} existing project(s)")

    def create_project(self, name, repo_url="", branch="main"):
        """
        Create a new project.

        Args:
            name: Project name (used as directory name)
            repo_url: GitHub repository URL
            branch: Default branch

        Returns:
            ProjectState instance

        Raises:
            ValueError: If project already exists
        """
        if name in self._projects:
            raise ValueError(f"Project '{name}' already exists")

        # Create project directory
        project_dir = self.projects_dir / name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (project_dir / "src").mkdir(exist_ok=True)
        (project_dir / "logs").mkdir(exist_ok=True)
        (project_dir / "patches").mkdir(exist_ok=True)

        # Create project state
        project = ProjectState(
            name=name,
            repo_url=repo_url,
            branch=branch,
        )

        # Save and cache
        project.save(self.states_dir)
        self._projects[name] = project

        self.logger.info(f"Created project: {name} (repo: {repo_url or 'none'})")
        return project

    def get_project(self, name):
        """
        Get a project by name.

        Args:
            name: Project name

        Returns:
            ProjectState or None
        """
        return self._projects.get(name)

    def list_projects(self):
        """
        List all projects with their status.

        Returns:
            list of dicts with project info
        """
        return [
            {
                "name": p.name,
                "status": p.status,
                "repo_url": p.repo_url,
                "container_id": p.container_id[:12] if p.container_id else None,
                "last_activity": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(p.last_activity)
                ),
            }
            for p in self._projects.values()
        ]

    def update_status(self, name, new_status):
        """
        Transition a project to a new status.

        Args:
            name: Project name
            new_status: Target status

        Raises:
            ValueError: If project not found or invalid transition
        """
        project = self.get_project(name)
        if not project:
            raise ValueError(f"Project '{name}' not found")

        old_status = project.status
        project.transition_to(new_status)
        project.save(self.states_dir)

        self.logger.info(
            f"Project '{name}': {old_status} → {new_status}"
        )

    def set_container(self, name, container_id, container_name=None):
        """Associate a Docker container with a project."""
        project = self.get_project(name)
        if not project:
            raise ValueError(f"Project '{name}' not found")

        project.container_id = container_id
        project.container_name = container_name
        project.last_activity = time.time()
        project.save(self.states_dir)

    def record_error(self, name, error_msg):
        """Record an error for a project."""
        project = self.get_project(name)
        if project:
            project.add_error(error_msg)
            project.save(self.states_dir)

    def get_idle_projects(self):
        """Get all projects in idle state (ready for work)."""
        return [
            p for p in self._projects.values()
            if p.status == ProjectStatus.IDLE
        ]

    def get_project_dir(self, name):
        """Get the filesystem path for a project."""
        return self.projects_dir / name

    def delete_project(self, name):
        """
        Remove a project (state only, not files).

        Args:
            name: Project name
        """
        if name in self._projects:
            state_file = self.states_dir / f"{name}.json"
            if state_file.exists():
                state_file.unlink()
            del self._projects[name]
            self.logger.info(f"Deleted project state: {name}")

    @property
    def project_count(self):
        """Total number of projects."""
        return len(self._projects)
