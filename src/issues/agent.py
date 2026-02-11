"""
GitHub Issue Agent for AIDEV-OPS.

Polls GitHub repositories for open issues every 5 minutes,
parses them into work items, and queues them for processing.
"""

import time
from github import Github, GithubException
from src.issues.parser import IssueParser
from src.logger import setup_logger


class IssueAgent:
    """
    GitHub issue polling and management agent.

    Features:
    - Polls for new/updated issues on a configurable interval
    - Parses issue metadata (priority, type, files)
    - Tracks processed issues to avoid duplicates
    - Comments on issues when work starts/completes
    - Closes issues after successful resolution
    """

    # Label indicating AIDEV-OPS should process this issue
    TRIGGER_LABEL = "aidev"

    # Label added when work is in progress
    WIP_LABEL = "aidev-wip"

    def __init__(self, config):
        """
        Initialize Issue Agent.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('issue_agent', config)
        self.parser = IssueParser()

        github_config = config.get('github', {})
        self.poll_interval = github_config.get('poll_interval', 300)
        pat = github_config.get('pat_token', '')

        self._processed_issues = set()  # Track processed issue numbers per repo
        self._github = None

        if pat and not pat.startswith('ghp_your'):
            try:
                self._github = Github(pat)
                self.logger.info("GitHub client initialized")
            except Exception as e:
                self.logger.error(f"Failed to init GitHub client: {e}")
        else:
            self.logger.warning("No valid GitHub PAT — issue polling disabled")

    def is_available(self):
        """Check if GitHub client is ready."""
        return self._github is not None

    def poll_issues(self, repo_name):
        """
        Poll a repository for open issues tagged for AIDEV-OPS.

        Args:
            repo_name: Repository in 'owner/repo' format

        Returns:
            list of parsed work item dicts, sorted by priority
        """
        if not self.is_available():
            self.logger.debug("GitHub not available, skipping poll")
            return []

        try:
            repo = self._github.get_repo(repo_name)
            issues = repo.get_issues(
                state='open',
                labels=[self.TRIGGER_LABEL],
                sort='created',
                direction='asc'
            )

            work_items = []
            for issue in issues:
                # Skip PRs (GitHub API returns PRs as issues too)
                if issue.pull_request:
                    continue

                # Skip already processed issues
                issue_key = f"{repo_name}#{issue.number}"
                if issue_key in self._processed_issues:
                    continue

                # Check if already being worked on
                issue_labels = [l.name.lower() for l in issue.labels]
                if self.WIP_LABEL in issue_labels:
                    continue

                work_item = self.parser.parse(issue)
                work_item['repo'] = repo_name
                work_items.append(work_item)

                self.logger.info(
                    f"Found issue #{issue.number}: {issue.title} "
                    f"(priority: {work_item['priority']})"
                )

            # Sort by priority (lower = higher priority)
            work_items.sort(key=lambda x: x['priority'])

            return work_items

        except GithubException as e:
            self.logger.error(f"GitHub API error polling {repo_name}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error polling issues: {e}")
            return []

    def mark_in_progress(self, repo_name, issue_number):
        """
        Mark an issue as being worked on.

        Args:
            repo_name: Repository name
            issue_number: Issue number
        """
        if not self.is_available():
            return

        try:
            repo = self._github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Add WIP label
            issue.add_to_labels(self.WIP_LABEL)

            # Comment
            issue.create_comment(
                "🤖 **AIDEV-OPS** is now working on this issue.\n\n"
                "I'll update this issue when the fix is ready."
            )

            issue_key = f"{repo_name}#{issue_number}"
            self._processed_issues.add(issue_key)

            self.logger.info(f"Marked issue #{issue_number} as in-progress")

        except GithubException as e:
            self.logger.error(f"Failed to mark issue #{issue_number}: {e}")

    def mark_resolved(self, repo_name, issue_number, commit_sha=None, summary=""):
        """
        Mark an issue as resolved and close it.

        Args:
            repo_name: Repository name
            issue_number: Issue number
            commit_sha: Optional commit SHA of the fix
            summary: Resolution summary
        """
        if not self.is_available():
            return

        try:
            repo = self._github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Comment with resolution
            comment = "✅ **AIDEV-OPS** has resolved this issue.\n\n"
            if summary:
                comment += f"**Summary:** {summary}\n\n"
            if commit_sha:
                comment += f"**Commit:** `{commit_sha}`\n"

            issue.create_comment(comment)

            # Remove WIP label and close
            try:
                issue.remove_from_labels(self.WIP_LABEL)
            except Exception:
                pass

            issue.edit(state='closed')

            self.logger.info(f"Resolved and closed issue #{issue_number}")

        except GithubException as e:
            self.logger.error(f"Failed to resolve issue #{issue_number}: {e}")

    def mark_blocked(self, repo_name, issue_number, reason):
        """
        Mark an issue as blocked with a reason.

        Args:
            repo_name: Repository name
            issue_number: Issue number
            reason: Why it's blocked
        """
        if not self.is_available():
            return

        try:
            repo = self._github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            issue.create_comment(
                f"⚠️ **AIDEV-OPS** is blocked on this issue.\n\n"
                f"**Reason:** {reason}\n\n"
                f"Manual intervention may be required."
            )

            issue.add_to_labels("blocked")

            self.logger.warning(
                f"Issue #{issue_number} blocked: {reason}"
            )

        except GithubException as e:
            self.logger.error(f"Failed to mark issue #{issue_number} blocked: {e}")

    def get_issue_comments(self, repo_name, issue_number):
        """Get all comments on an issue."""
        if not self.is_available():
            return []

        try:
            repo = self._github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            return [
                {
                    "user": c.user.login,
                    "body": c.body,
                    "created_at": c.created_at.isoformat(),
                }
                for c in issue.get_comments()
            ]
        except Exception:
            return []
