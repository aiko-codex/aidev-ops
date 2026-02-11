"""
Issue Metadata Parser for AIDEV-OPS.

Extracts structured data from GitHub issue body and labels:
priority, affected files, issue type, and constraints.
"""

import re


class IssueParser:
    """
    Parse GitHub issues into structured work items.

    Supports label-based and body-based metadata extraction.
    """

    # Known labels and their mappings
    PRIORITY_LABELS = {
        'critical': 1,
        'high': 2,
        'priority:high': 2,
        'medium': 3,
        'priority:medium': 3,
        'low': 4,
        'priority:low': 4,
    }

    TYPE_LABELS = {
        'bug': 'bugfix',
        'bugfix': 'bugfix',
        'feature': 'feature',
        'enhancement': 'feature',
        'refactor': 'refactor',
        'docs': 'documentation',
        'documentation': 'documentation',
        'test': 'testing',
    }

    def parse(self, issue):
        """
        Parse a GitHub issue into a work item dict.

        Args:
            issue: PyGithub Issue object

        Returns:
            dict with structured metadata
        """
        labels = [l.name.lower() for l in issue.labels]

        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "priority": self._extract_priority(labels, issue.body or ""),
            "type": self._extract_type(labels),
            "affected_files": self._extract_files(issue.body or ""),
            "constraints": self._extract_constraints(issue.body or ""),
            "assignee": issue.assignee.login if issue.assignee else None,
            "labels": labels,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "url": issue.html_url,
        }

    def _extract_priority(self, labels, body):
        """Extract priority from labels or body."""
        # Check labels first
        for label in labels:
            if label in self.PRIORITY_LABELS:
                return self.PRIORITY_LABELS[label]

        # Check body for priority markers
        body_lower = body.lower()
        if 'urgent' in body_lower or 'critical' in body_lower:
            return 1
        if 'high priority' in body_lower:
            return 2

        return 3  # Default: medium

    def _extract_type(self, labels):
        """Extract issue type from labels."""
        for label in labels:
            if label in self.TYPE_LABELS:
                return self.TYPE_LABELS[label]
        return 'bugfix'  # Default

    def _extract_files(self, body):
        """
        Extract affected file paths from issue body.

        Looks for patterns like:
        - File: path/to/file.php
        - `path/to/file.php`
        - **Files:** file1.php, file2.php
        """
        files = []

        # Pattern: File: path/to/file
        file_pattern = re.compile(
            r'(?:file|path|location)s?\s*:\s*[`]*([^\s`\n,]+\.\w+)[`]*',
            re.IGNORECASE
        )
        files.extend(file_pattern.findall(body))

        # Pattern: backtick-wrapped paths
        backtick_pattern = re.compile(r'`([^`]+\.\w{1,5})`')
        for match in backtick_pattern.findall(body):
            # Filter to likely file paths
            if '/' in match or '.' in match:
                if not match.startswith('http'):
                    files.append(match)

        return list(set(files))

    def _extract_constraints(self, body):
        """Extract any mentioned constraints from the body."""
        constraints = []

        body_lower = body.lower()
        if 'php 5.6' in body_lower:
            constraints.append('php56')
        if 'mysqli' in body_lower:
            constraints.append('mysqli')
        if 'bootstrap' in body_lower:
            constraints.append('bootstrap4')
        if 'no framework' in body_lower:
            constraints.append('no_framework')

        return constraints
