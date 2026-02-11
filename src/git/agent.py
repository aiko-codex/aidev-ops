"""
Git Agent for AIDEV-OPS.

Handles all Git operations: clone, pull, branch, commit, push, tag.
Uses subprocess for git commands with PAT authentication.
"""

import subprocess
import time
from pathlib import Path
from src.logger import setup_logger


class GitAgent:
    """
    Git operations agent for autonomous repository management.

    Features:
    - Clone repositories with PAT authentication
    - Pull latest before work, push after
    - Branch management (aidev/* prefix)
    - Auto-commit with structured messages
    - Release tagging
    - Conflict detection and rebase
    """

    def __init__(self, config):
        """
        Initialize Git Agent.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('git_agent', config)
        self.github_config = config.get('github', {})

        self.pat_token = self.github_config.get('pat_token', '')
        self.auto_commit = self.github_config.get('auto_commit', True)
        self.auto_push = self.github_config.get('auto_push', True)
        self.branch_prefix = self.github_config.get('branch_prefix', 'aidev/')

    def _run_git(self, args, cwd=None, timeout=120):
        """
        Run a git command and return output.

        Args:
            args: List of git arguments (without 'git' prefix)
            cwd: Working directory
            timeout: Command timeout in seconds

        Returns:
            tuple: (success: bool, output: str)
        """
        cmd = ['git'] + args

        # Mask PAT in logs
        log_cmd = ' '.join(cmd)
        if self.pat_token and self.pat_token in log_cmd:
            log_cmd = log_cmd.replace(self.pat_token, '***PAT***')
        self.logger.debug(f"Running: {log_cmd}")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._get_env()
            )

            if result.returncode == 0:
                return (True, result.stdout.strip())
            else:
                self.logger.warning(
                    f"Git command failed: {result.stderr.strip()}"
                )
                return (False, result.stderr.strip())

        except subprocess.TimeoutExpired:
            self.logger.error(f"Git command timed out after {timeout}s")
            return (False, "Command timed out")
        except FileNotFoundError:
            self.logger.error("Git is not installed or not in PATH")
            return (False, "Git not found")

    def _get_env(self):
        """Get environment dict with git config."""
        import os
        env = os.environ.copy()
        # Disable interactive prompts
        env['GIT_TERMINAL_PROMPT'] = '0'
        return env

    def _get_auth_url(self, repo_url):
        """Insert PAT token into clone URL for authentication."""
        if not self.pat_token or not repo_url:
            return repo_url

        # Convert https://github.com/user/repo.git
        # to     https://PAT@github.com/user/repo.git
        if repo_url.startswith('https://'):
            return repo_url.replace('https://', f'https://{self.pat_token}@')
        return repo_url

    def clone(self, repo_url, target_dir, branch=None):
        """
        Clone a repository.

        Args:
            repo_url: Repository URL
            target_dir: Where to clone to
            branch: Optional branch to checkout

        Returns:
            bool: Success
        """
        target_dir = Path(target_dir)
        auth_url = self._get_auth_url(repo_url)

        # If target exists and has .git, it's already cloned — pull instead
        if (target_dir / '.git').exists():
            self.logger.info(f"Already cloned at {target_dir}, pulling instead")
            return self.pull(str(target_dir))

        # If target exists but is empty (created by ProjectManager), remove it
        # so git clone can create it fresh
        if target_dir.exists():
            try:
                if not any(target_dir.iterdir()):
                    target_dir.rmdir()
                else:
                    self.logger.error(
                        f"Target dir {target_dir} exists and is not empty"
                    )
                    return False
            except Exception as e:
                self.logger.error(f"Cannot prepare target dir: {e}")
                return False

        args = ['clone']
        if branch:
            args += ['-b', branch]
        args += [auth_url, str(target_dir)]

        self.logger.info(f"Cloning {repo_url} → {target_dir}")
        success, output = self._run_git(args, timeout=300)

        if success:
            self.logger.info(f"Clone successful")
            # Set safe directory
            self._run_git(
                ['config', '--global', '--add', 'safe.directory', str(target_dir)]
            )
        else:
            self.logger.error(f"Clone failed: {output}")

        return success

    def pull(self, project_dir, branch=None):
        """
        Pull latest changes.

        Args:
            project_dir: Project directory path
            branch: Branch to pull (default: current)

        Returns:
            bool: Success
        """
        args = ['pull', 'origin']
        if branch:
            args.append(branch)

        self.logger.info(f"Pulling latest for {project_dir}")
        success, output = self._run_git(args, cwd=str(project_dir))
        return success

    def create_branch(self, project_dir, branch_name):
        """
        Create and checkout a new branch.

        Args:
            project_dir: Project directory path
            branch_name: Branch name (prefix will be added)

        Returns:
            bool: Success
        """
        full_branch = f"{self.branch_prefix}{branch_name}"

        success, _ = self._run_git(
            ['checkout', '-b', full_branch],
            cwd=str(project_dir)
        )

        if success:
            self.logger.info(f"Created branch: {full_branch}")
        return success

    def commit(self, project_dir, message, files=None):
        """
        Stage and commit changes.

        Args:
            project_dir: Project directory path
            message: Commit message
            files: Specific files to stage (None = all)

        Returns:
            bool: Success
        """
        cwd = str(project_dir)

        # Stage files
        if files:
            for f in files:
                self._run_git(['add', f], cwd=cwd)
        else:
            self._run_git(['add', '-A'], cwd=cwd)

        # Check if there are staged changes
        success, status = self._run_git(['status', '--porcelain'], cwd=cwd)
        if not status.strip():
            self.logger.info("No changes to commit")
            return True

        # Commit
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[AIDEV-OPS] {message}\n\nAutomated commit at {timestamp}"

        success, output = self._run_git(
            ['commit', '-m', full_message],
            cwd=cwd
        )

        if success:
            self.logger.info(f"Committed: {message}")
        return success

    def push(self, project_dir, branch=None, force=False):
        """
        Push to remote.

        Args:
            project_dir: Project directory path
            branch: Branch to push (default: current)
            force: Force push

        Returns:
            bool: Success
        """
        args = ['push', 'origin']
        if branch:
            args.append(branch)
        if force:
            args.append('--force')

        self.logger.info(f"Pushing to remote")
        success, output = self._run_git(args, cwd=str(project_dir))

        if not success and 'rejected' in output.lower():
            self.logger.warning("Push rejected, attempting rebase")
            return self._rebase_and_push(project_dir, branch)

        return success

    def _rebase_and_push(self, project_dir, branch=None):
        """Rebase on remote and retry push."""
        cwd = str(project_dir)
        args = ['pull', '--rebase', 'origin']
        if branch:
            args.append(branch)

        success, _ = self._run_git(args, cwd=cwd)
        if success:
            return self.push(project_dir, branch)
        return False

    def tag(self, project_dir, tag_name, message=None):
        """
        Create a git tag.

        Args:
            project_dir: Project directory
            tag_name: Tag name
            message: Tag message

        Returns:
            bool: Success
        """
        args = ['tag']
        if message:
            args += ['-a', tag_name, '-m', message]
        else:
            args.append(tag_name)

        success, _ = self._run_git(args, cwd=str(project_dir))
        if success:
            # Push tag
            self._run_git(['push', 'origin', tag_name], cwd=str(project_dir))
            self.logger.info(f"Tagged: {tag_name}")
        return success

    def get_status(self, project_dir):
        """
        Get current git status.

        Returns:
            dict with branch, status, last commit info
        """
        cwd = str(project_dir)

        _, branch = self._run_git(['branch', '--show-current'], cwd=cwd)
        _, status = self._run_git(['status', '--porcelain'], cwd=cwd)
        _, last_commit = self._run_git(
            ['log', '-1', '--format=%h %s'], cwd=cwd
        )

        return {
            "branch": branch,
            "clean": not bool(status.strip()),
            "changed_files": len(status.strip().split('\n')) if status.strip() else 0,
            "last_commit": last_commit,
        }

    def get_diff(self, project_dir, staged=False):
        """Get the current diff."""
        args = ['diff']
        if staged:
            args.append('--staged')

        _, diff = self._run_git(args, cwd=str(project_dir))
        return diff
