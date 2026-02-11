"""
Codebase Context Builder for AIDEV-OPS.

After pulling a repo, this module scans the codebase and builds
a context package for the AI. The context includes:
1. Project file tree (structure overview)
2. Contents of files mentioned in the issue
3. Contents of related files (detected via imports/includes)
4. A project summary (README, config files)

This is what tells the AI "what to work on" — it bridges the gap
between a GitHub issue description and the actual code.
"""

import os
import re
from pathlib import Path
from src.logger import setup_logger


class ContextBuilder:
    """
    Builds codebase context for AI consumption.

    The AI can't see your repo — this module reads it,
    summarizes the structure, and extracts relevant file
    contents so the AI knows what it's working with.
    """

    # File extensions to include in tree scan
    CODE_EXTENSIONS = {
        '.php', '.html', '.htm', '.css', '.js',
        '.py', '.json', '.xml', '.yml', '.yaml',
        '.sql', '.sh', '.bash', '.md', '.txt',
        '.conf', '.cfg', '.ini', '.env.example',
    }

    # Files to always skip
    SKIP_PATTERNS = {
        'node_modules', 'vendor', '.git', '__pycache__',
        '.idea', '.vscode', 'dist', 'build', '.cache',
        'storage/logs', 'storage/framework',
    }

    # Max file size to read (avoid huge files)
    MAX_FILE_SIZE = 50_000  # 50KB

    # Max total context size (to fit in AI token limits)
    MAX_CONTEXT_SIZE = 30_000  # ~30K chars ≈ ~8K tokens

    def __init__(self, config):
        self.config = config
        self.logger = setup_logger('context_builder', config)

    def build_context(self, project_dir, issue=None):
        """
        Build full context package for the AI.

        Args:
            project_dir: Path to the project root
            issue: Optional parsed issue dict (from IssueParser)

        Returns:
            str: Formatted context string ready for AI consumption
        """
        project_dir = Path(project_dir)
        sections = []

        # 1. Project overview (file tree)
        tree = self.get_file_tree(project_dir)
        sections.append(f"## Project Structure\n```\n{tree}\n```")

        # 2. Project summary (README, etc.)
        summary = self._read_project_summary(project_dir)
        if summary:
            sections.append(f"## Project Summary\n{summary}")

        # 3. Issue-specific files
        if issue:
            affected_files = issue.get('affected_files', [])
            if affected_files:
                file_contents = self._read_files(project_dir, affected_files)
                if file_contents:
                    sections.append(f"## Affected Files\n{file_contents}")

            # Also try to find related files from the issue body
            mentioned = self._find_mentioned_files(
                issue.get('body', ''), project_dir
            )
            if mentioned:
                extra = self._read_files(project_dir, mentioned)
                if extra:
                    sections.append(f"## Related Files\n{extra}")

        context = "\n\n".join(sections)

        # Trim if too long
        if len(context) > self.MAX_CONTEXT_SIZE:
            context = context[:self.MAX_CONTEXT_SIZE] + "\n\n... (context truncated)"

        self.logger.info(
            f"Built context for {project_dir.name}: "
            f"{len(context)} chars, {len(sections)} sections"
        )

        return context

    def get_file_tree(self, project_dir, max_depth=4):
        """
        Generate a file tree string showing project structure.

        Args:
            project_dir: Project root path
            max_depth: Maximum directory depth to show

        Returns:
            str: Formatted file tree
        """
        lines = []
        project_dir = Path(project_dir)

        def _walk(directory, prefix="", depth=0):
            if depth >= max_depth:
                return

            try:
                entries = sorted(
                    directory.iterdir(),
                    key=lambda e: (not e.is_dir(), e.name.lower())
                )
            except PermissionError:
                return

            # Filter out skip patterns
            entries = [
                e for e in entries
                if not any(skip in str(e) for skip in self.SKIP_PATTERNS)
            ]

            for i, entry in enumerate(entries):
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                extension = "    " if is_last else "│   "

                if entry.is_dir():
                    child_count = sum(1 for _ in entry.iterdir()) if entry.exists() else 0
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    if child_count > 0:
                        _walk(entry, prefix + extension, depth + 1)
                else:
                    if entry.suffix.lower() in self.CODE_EXTENSIONS or entry.name in {
                        'Dockerfile', 'Makefile', '.gitignore', '.htaccess',
                        'composer.json', 'package.json',
                    }:
                        size = entry.stat().st_size
                        size_str = self._format_size(size)
                        lines.append(f"{prefix}{connector}{entry.name} ({size_str})")

        lines.append(f"{project_dir.name}/")
        _walk(project_dir)

        return "\n".join(lines[:100])  # Cap at 100 lines

    def read_file_content(self, file_path):
        """
        Read a single file's content safely.

        Args:
            file_path: Path to file

        Returns:
            str: File content or error message
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return f"[File not found: {file_path.name}]"

        if file_path.stat().st_size > self.MAX_FILE_SIZE:
            return f"[File too large: {file_path.name} ({self._format_size(file_path.stat().st_size)})]"

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            return f"[Error reading {file_path.name}: {e}]"

    def _read_files(self, project_dir, file_paths):
        """Read multiple files and format them."""
        project_dir = Path(project_dir)
        parts = []
        total_size = 0

        for rel_path in file_paths:
            if total_size > self.MAX_CONTEXT_SIZE // 2:
                parts.append("... (remaining files skipped to save context space)")
                break

            full_path = project_dir / rel_path
            content = self.read_file_content(full_path)

            # Determine language for code block
            ext = Path(rel_path).suffix.lstrip('.')
            lang_map = {
                'php': 'php', 'js': 'javascript', 'css': 'css',
                'html': 'html', 'py': 'python', 'sql': 'sql',
                'json': 'json', 'yaml': 'yaml', 'yml': 'yaml',
                'sh': 'bash', 'bash': 'bash', 'xml': 'xml',
            }
            lang = lang_map.get(ext, '')

            parts.append(
                f"### `{rel_path}`\n```{lang}\n{content}\n```"
            )
            total_size += len(content)

        return "\n\n".join(parts)

    def _read_project_summary(self, project_dir):
        """Read README and key config files for project overview."""
        project_dir = Path(project_dir)
        summaries = []

        # Look for README
        for readme in ['README.md', 'README.txt', 'readme.md']:
            readme_path = project_dir / readme
            if readme_path.exists():
                content = self.read_file_content(readme_path)
                # Take first 2000 chars of README
                summaries.append(content[:2000])
                break

        # Look for composer.json or package.json (project metadata)
        for meta_file in ['composer.json', 'package.json']:
            meta_path = project_dir / meta_file
            if meta_path.exists():
                content = self.read_file_content(meta_path)
                summaries.append(f"**{meta_file}:**\n```json\n{content[:1000]}\n```")

        return "\n\n".join(summaries) if summaries else None

    def _find_mentioned_files(self, text, project_dir):
        """
        Find file paths mentioned in issue body that exist in the project.

        Args:
            text: Issue body text
            project_dir: Project root path

        Returns:
            list: File paths that exist in the project
        """
        project_dir = Path(project_dir)
        found = []

        # Pattern: anything that looks like a file path with extension
        path_pattern = re.compile(r'[\w./\\-]+\.\w{1,5}')
        candidates = path_pattern.findall(text)

        for candidate in candidates:
            # Normalize path
            candidate = candidate.replace('\\', '/')
            full_path = project_dir / candidate

            if full_path.exists() and full_path.is_file():
                if candidate not in found:
                    found.append(candidate)

        return found[:10]  # Max 10 related files

    def find_related_files(self, project_dir, target_file):
        """
        Find files related to a target file via imports/includes.

        For PHP: looks for include/require statements
        For JS: looks for import/require statements
        For Python: looks for import statements

        Args:
            project_dir: Project root
            target_file: Path to the target file

        Returns:
            list: Paths to related files
        """
        project_dir = Path(project_dir)
        target = project_dir / target_file
        related = []

        if not target.exists():
            return related

        content = self.read_file_content(target)

        # PHP includes
        if target.suffix == '.php':
            patterns = [
                re.compile(r"(?:include|require)(?:_once)?\s*[('\"]([^'\"]+)['\"]"),
            ]
            for pattern in patterns:
                for match in pattern.findall(content):
                    rel_path = match.replace('\\', '/')
                    full = project_dir / rel_path
                    if full.exists():
                        related.append(rel_path)

        # JavaScript imports
        elif target.suffix == '.js':
            patterns = [
                re.compile(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]"),
            ]
            for pattern in patterns:
                for match in pattern.findall(content):
                    if not match.startswith(('http', 'node:')):
                        related.append(match)

        return list(set(related))[:10]

    def _format_size(self, size_bytes):
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
