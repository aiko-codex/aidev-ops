"""
Agent Core — Main Orchestrator for AIDEV-OPS.

Initializes all modules and runs the main event loop:
poll issues → process → commit. Handles signals and graceful shutdown.
"""

import time
import signal
import sys
import json
from pathlib import Path
from src.config import load_config, get_data_dir, get_log_dir
from src.logger import setup_logger, log_separator
from src.ai.gateway import AIGateway
from src.project.manager import ProjectManager
from src.docker_engine.engine import DockerEngine
from src.git.agent import GitAgent
from src.issues.agent import IssueAgent
from src.workflow.executor import WorkflowExecutor


class AgentCore:
    """
    Central orchestrator for the AIDEV-OPS system.

    Responsibilities:
    - Initialize all subsystem modules
    - Run the main polling loop
    - Handle shutdown signals (SIGTERM, SIGINT)
    - Checkpoint and recover state
    - Log system-wide events
    """

    def __init__(self, config=None):
        """
        Initialize the Agent Core.

        Args:
            config: Optional pre-loaded config dict. If None, loads from file.
        """
        self.config = config or load_config()
        self.logger = setup_logger('core', self.config)
        self.running = False
        self._setup_signal_handlers()

        log_separator(self.logger, "AIDEV-OPS Initializing")

        # Initialize all modules
        self.ai_gateway = AIGateway(self.config)
        self.project_manager = ProjectManager(self.config)
        self.docker_engine = DockerEngine(self.config)
        self.git_agent = GitAgent(self.config)
        self.issue_agent = IssueAgent(self.config)
        self.workflow = WorkflowExecutor(
            self.config,
            self.ai_gateway,
            self.project_manager,
            self.docker_engine,
            self.git_agent,
        )

        # State tracking
        self.cycle_count = 0
        self.start_time = None
        self.last_poll = 0

        log_separator(self.logger, "Initialization Complete")

    def _setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name} — shutting down gracefully...")
        self.running = False

    def start(self):
        """
        Start the main event loop.

        This runs continuously, polling for issues and processing them.
        """
        self.running = True
        self.start_time = time.time()

        log_separator(self.logger, "AIDEV-OPS Started")
        self.logger.info(f"Server mode: {self.config.get('server', {}).get('mode', 'unknown')}")
        self.logger.info(f"Projects: {self.project_manager.project_count}")
        self.logger.info(f"Docker: {'available' if self.docker_engine.is_available() else 'unavailable'}")
        self.logger.info(f"GitHub: {'available' if self.issue_agent.is_available() else 'unavailable'}")
        self.logger.info(f"AI roles: {list(self.ai_gateway.available_roles.keys())}")

        poll_interval = self.config.get('github', {}).get('poll_interval', 300)

        # Write PID file
        self._write_pid()

        try:
            while self.running:
                self.cycle_count += 1
                self.logger.debug(f"── Cycle #{self.cycle_count} ──")

                # Process each project
                for project in self.project_manager.list_projects():
                    if not self.running:
                        break

                    if project['status'] == 'idle' and project.get('repo_url'):
                        self._process_project(project)

                # Wait before next poll
                self.logger.debug(f"Sleeping {poll_interval}s until next poll...")
                for _ in range(poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        finally:
            self._cleanup()

    def _process_project(self, project_info):
        """
        Process a single project: poll issues and execute fixes.

        Args:
            project_info: Project dict from list_projects()
        """
        name = project_info['name']
        project = self.project_manager.get_project(name)

        if not project or not project.repo_url:
            return

        repo_name = self._repo_url_to_name(project.repo_url)
        if not repo_name:
            return

        # Poll for issues
        work_items = self.issue_agent.poll_issues(repo_name)
        if not work_items:
            return

        self.logger.info(f"Found {len(work_items)} issue(s) for {name}")

        for item in work_items:
            if not self.running:
                break

            try:
                # Mark as in-progress
                self.project_manager.update_status(name, 'building')
                self.issue_agent.mark_in_progress(repo_name, item['number'])

                # Pull latest code
                project_dir = self.project_manager.get_project_dir(name)
                self.git_agent.pull(project_dir)

                # Execute workflow
                result = self.workflow.execute(item)

                if result['success']:
                    self.issue_agent.mark_resolved(
                        repo_name, item['number'],
                        commit_sha=result.get('commit_sha'),
                        summary=result.get('summary', '')
                    )
                    self.project_manager.update_status(name, 'idle')
                    project.commit_count += 1
                else:
                    errors = '; '.join(result.get('errors', ['Unknown error']))
                    self.issue_agent.mark_blocked(
                        repo_name, item['number'], errors
                    )
                    self.project_manager.record_error(name, errors)
                    self.project_manager.update_status(name, 'blocked')
                    # Reset to idle to try other issues
                    self.project_manager.update_status(name, 'idle')

            except Exception as e:
                self.logger.error(f"Error processing issue #{item['number']}: {e}")
                self.project_manager.record_error(name, str(e))
                try:
                    self.project_manager.update_status(name, 'idle')
                except Exception:
                    pass

    def _repo_url_to_name(self, repo_url):
        """Convert GitHub URL to owner/repo format."""
        if not repo_url:
            return None
        # https://github.com/owner/repo.git → owner/repo
        url = repo_url.rstrip('/')
        if url.endswith('.git'):
            url = url[:-4]
        parts = url.split('/')
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return None

    def stop(self):
        """Stop the event loop."""
        self.running = False
        self.logger.info("Stop requested")

    def status(self):
        """
        Get current system status.

        Returns:
            dict with system information
        """
        uptime = time.time() - self.start_time if self.start_time else 0

        return {
            "running": self.running,
            "uptime_seconds": int(uptime),
            "uptime_human": self._format_uptime(uptime),
            "cycles": self.cycle_count,
            "projects": self.project_manager.list_projects(),
            "project_count": self.project_manager.project_count,
            "docker_available": self.docker_engine.is_available(),
            "github_available": self.issue_agent.is_available(),
            "ai_gateway": self.ai_gateway.stats,
            "ai_roles": self.ai_gateway.available_roles,
        }

    def _format_uptime(self, seconds):
        """Format seconds into human-readable uptime."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def _write_pid(self):
        """Write PID file for process management."""
        pid_file = self.config.get('server', {}).get('pid_file', '/opt/aidev/aidev.pid')
        try:
            Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    def _cleanup(self):
        """Cleanup on shutdown."""
        log_separator(self.logger, "AIDEV-OPS Shutting Down")
        self.logger.info(f"Total cycles: {self.cycle_count}")

        # Remove PID file
        pid_file = self.config.get('server', {}).get('pid_file', '/opt/aidev/aidev.pid')
        try:
            Path(pid_file).unlink(missing_ok=True)
        except Exception:
            pass

        self.logger.info("Shutdown complete")


# Need os for PID
import os
