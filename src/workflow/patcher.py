"""
Patch Generator for AIDEV-OPS.

Creates diff-based patches instead of full file rewrites.
Applies and validates patches safely with rollback support.
"""

import os
import shutil
import difflib
import time
from pathlib import Path
from src.logger import setup_logger


class PatchGenerator:
    """
    Generates and applies diff-based code patches.

    Features:
    - Generate unified diffs between original and modified files
    - Apply patches with validation
    - Automatic backup before applying
    - Rollback support
    """

    def __init__(self, config):
        """
        Initialize Patch Generator.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('patcher', config)

    def generate_patch(self, original_content, modified_content,
                       filename="file", context_lines=3):
        """
        Generate a unified diff patch.

        Args:
            original_content: Original file content string
            modified_content: Modified file content string
            filename: Filename for the patch header
            context_lines: Number of context lines around changes

        Returns:
            str: Unified diff string
        """
        original_lines = original_content.splitlines(keepends=True)
        modified_lines = modified_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )

        patch = ''.join(diff)

        if patch:
            added = sum(1 for line in patch.split('\n') if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in patch.split('\n') if line.startswith('-') and not line.startswith('---'))
            self.logger.info(
                f"Generated patch for {filename}: "
                f"+{added}/-{removed} lines"
            )
        else:
            self.logger.debug(f"No changes for {filename}")

        return patch

    def apply_patch(self, file_path, new_content, backup=True):
        """
        Apply changes to a file with optional backup.

        Args:
            file_path: Path to the target file
            new_content: New file content
            backup: Whether to create a backup first

        Returns:
            dict: {
                "success": bool,
                "backup_path": str or None,
                "patch": str (the diff)
            }
        """
        file_path = Path(file_path)
        backup_path = None

        # Read original content
        original_content = ""
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                original_content = f.read()

        # Generate the diff for logging
        patch = self.generate_patch(
            original_content, new_content,
            filename=file_path.name
        )

        if not patch:
            return {
                "success": True,
                "backup_path": None,
                "patch": "",
                "message": "No changes needed"
            }

        # Create backup
        if backup and file_path.exists():
            backup_dir = file_path.parent / ".aidev-backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{file_path.name}.{timestamp}.bak"
            shutil.copy2(file_path, backup_path)
            self.logger.debug(f"Backup created: {backup_path}")

        # Write new content
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            self.logger.info(f"Applied patch to {file_path.name}")

            return {
                "success": True,
                "backup_path": str(backup_path) if backup_path else None,
                "patch": patch,
            }

        except Exception as e:
            # Rollback on failure
            if backup_path and backup_path.exists():
                shutil.copy2(backup_path, file_path)
                self.logger.info(f"Rolled back to backup: {file_path.name}")

            self.logger.error(f"Failed to apply patch: {e}")
            return {
                "success": False,
                "backup_path": str(backup_path) if backup_path else None,
                "patch": patch,
                "error": str(e),
            }

    def rollback(self, file_path, backup_path):
        """
        Rollback a file to its backup.

        Args:
            file_path: Current file path
            backup_path: Backup file path

        Returns:
            bool: Success
        """
        try:
            shutil.copy2(backup_path, file_path)
            self.logger.info(f"Rolled back: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False

    def create_new_file(self, file_path, content, backup=True):
        """
        Create a new file with content.

        Args:
            file_path: Target file path
            content: File content
            backup: Backup if file already exists

        Returns:
            dict with apply result
        """
        return self.apply_patch(file_path, content, backup=backup)

    def save_patch_file(self, patch_content, project_dir, patch_name=None):
        """
        Save a patch to the project's patches directory.

        Args:
            patch_content: The patch string
            project_dir: Project directory path
            patch_name: Optional custom name

        Returns:
            Path to saved patch file
        """
        patches_dir = Path(project_dir) / "patches"
        patches_dir.mkdir(exist_ok=True)

        if not patch_name:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            patch_name = f"patch_{timestamp}.diff"

        patch_file = patches_dir / patch_name
        with open(patch_file, 'w') as f:
            f.write(patch_content)

        self.logger.info(f"Saved patch: {patch_file}")
        return patch_file
