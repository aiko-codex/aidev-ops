"""
Project Kickstart for AIDEV-OPS.

Bootstraps a project from a PRD (Product Requirements Document).
Instead of waiting for GitHub issues, this reads the PRD.md,
sends it to the Planner AI to break it down, then executes
the plan step by step.

Usage:
    aidev kickstart todox
"""

import json
import time
from pathlib import Path
from src.logger import setup_logger
from src.workflow.context import ContextBuilder


class Kickstarter:
    """
    Bootstrap a project from a PRD document.

    Flow:
    1. Read PRD.md from the project repo
    2. Send to Planner AI → get task breakdown
    3. For each task → send to Architect → get file plan
    4. For each file → send to Coder → generate code
    5. Review → Apply → Commit → Push
    """

    def __init__(self, config, ai_gateway, project_manager,
                 docker_engine, git_agent):
        self.config = config
        self.logger = setup_logger('kickstart', config)
        self.ai = ai_gateway
        self.projects = project_manager
        self.docker = docker_engine
        self.git = git_agent
        self.context_builder = ContextBuilder(config)

    def kickstart(self, project_name, prd_path=None):
        """
        Main entry point: read PRD and build the project.

        Args:
            project_name: Registered project name
            prd_path: Optional custom PRD path (default: auto-detect)

        Returns:
            dict with results
        """
        self.logger.info(f"═══ Kickstarting project: {project_name}")

        project = self.projects.get_project(project_name)
        if not project:
            return {"success": False, "error": f"Project '{project_name}' not found"}

        project_dir = self.projects.get_project_dir(project_name)

        # Step 1: Find and read the PRD
        prd_content = self._read_prd(project_dir, prd_path)
        if not prd_content:
            return {"success": False, "error": "No PRD.md found in project"}

        self.logger.info(f"PRD loaded: {len(prd_content)} chars")

        # Step 2: Get task breakdown from Planner
        self.logger.info("[Step 1/4] Breaking down PRD into tasks...")
        tasks = self._plan_tasks(prd_content, project_dir)
        if not tasks:
            return {"success": False, "error": "Planning failed"}

        self.logger.info(f"Generated {len(tasks)} tasks")

        # Step 3: For each task, get architecture + code
        results = []
        for i, task in enumerate(tasks, 1):
            if not task.get('title'):
                continue

            self.logger.info(
                f"[Step 2/4] Task {i}/{len(tasks)}: {task['title']}"
            )

            # Get architecture plan
            architecture = self._architect_task(task, prd_content, project_dir)
            if not architecture:
                self.logger.warning(f"Architecture failed for task {i}, skipping")
                results.append({"task": task['title'], "status": "arch_failed"})
                continue

            # Generate code
            self.logger.info(f"[Step 3/4] Generating code for task {i}...")
            code_files = self._code_task(task, architecture, prd_content, project_dir)
            if not code_files:
                self.logger.warning(f"Code generation failed for task {i}")
                results.append({"task": task['title'], "status": "code_failed"})
                continue

            # Review and apply
            self.logger.info(f"[Step 4/4] Reviewing & applying task {i}...")
            from src.workflow.reviewer import ReviewAgent
            reviewer = ReviewAgent(self.config, self.ai)

            all_passed = True
            for filename, content in code_files.items():
                review = reviewer.review(content, filename)
                if not review['passed']:
                    self.logger.warning(
                        f"Review blocked {filename}: "
                        f"{review['issue_count']} issues"
                    )
                    all_passed = False
                    break

            if not all_passed:
                results.append({"task": task['title'], "status": "review_blocked"})
                continue

            # Write files
            for filename, content in code_files.items():
                file_path = project_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logger.info(f"  ✅ Created: {filename}")

            results.append({
                "task": task['title'],
                "status": "success",
                "files": list(code_files.keys())
            })

            # Commit after each task
            self.git.commit(
                str(project_dir),
                f"feat: {task['title']}\n\nKickstarted from PRD by AIDEV-OPS"
            )

        # Final push
        self.logger.info("Pushing all changes...")
        self.git.push(str(project_dir))

        success_count = sum(1 for r in results if r['status'] == 'success')
        self.logger.info(
            f"═══ Kickstart complete: {success_count}/{len(results)} tasks succeeded"
        )

        return {
            "success": success_count > 0,
            "total_tasks": len(results),
            "completed": success_count,
            "results": results,
        }

    def _read_prd(self, project_dir, custom_path=None):
        """Find and read the PRD document."""
        project_dir = Path(project_dir)

        # Check custom path first
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                return p.read_text(encoding='utf-8', errors='replace')

        # Auto-detect PRD files
        prd_names = [
            'PRD.md', 'prd.md', 'PRD.txt',
            'REQUIREMENTS.md', 'requirements.md',
            'SPEC.md', 'spec.md',
            'docs/PRD.md', 'docs/prd.md',
        ]

        for name in prd_names:
            prd_file = project_dir / name
            if prd_file.exists():
                self.logger.info(f"Found PRD: {name}")
                return prd_file.read_text(encoding='utf-8', errors='replace')

        return None

    def _plan_tasks(self, prd_content, project_dir):
        """Use Planner AI to break PRD into ordered tasks."""
        try:
            prompt = f"""You are a senior software architect. Read this PRD and break it down 
into a sequence of implementation tasks. Order them by dependency 
(foundation first, features later).

PRD:
{prd_content[:8000]}

Output as JSON array — each item must have:
- "title": short task title
- "description": what to implement
- "files": list of files to create/modify
- "dependencies": list of task titles this depends on

Example:
[
  {{
    "title": "Database schema",
    "description": "Create the database tables for users, tasks, etc.",
    "files": ["database/schema.sql", "database/seed.sql"],
    "dependencies": []
  }},
  {{
    "title": "User authentication",
    "description": "Login/register with session management",
    "files": ["auth/login.php", "auth/register.php", "includes/auth.php"],
    "dependencies": ["Database schema"]
  }}
]

Output ONLY the JSON array, no other text."""

            response = self.ai.plan(prompt)
            return self._parse_json_response(response)

        except Exception as e:
            self.logger.error(f"Task planning failed: {e}")
            return None

    def _architect_task(self, task, prd_content, project_dir):
        """Use Architect AI to design the implementation for a task."""
        try:
            # Get current project state
            context = self.context_builder.build_context(project_dir)

            prompt = f"""Design the implementation for this task.

Task: {task['title']}
Description: {task['description']}
Files to create: {', '.join(task.get('files', []))}

Project PRD (summary):
{prd_content[:3000]}

Provide:
1. File-by-file implementation plan
2. Key functions/classes for each file
3. How files connect to each other
4. Any database queries needed

Be specific — the Coder AI will use your design to write the actual code."""

            return self.ai.chat('architect', prompt, context=context)

        except Exception as e:
            self.logger.error(f"Architecture failed: {e}")
            return None

    def _code_task(self, task, architecture, prd_content, project_dir):
        """Use Coder AI to generate the actual code files."""
        try:
            context = self.context_builder.build_context(project_dir)

            prompt = f"""Generate the code for this task.

Task: {task['title']}
Description: {task['description']}

Architecture Plan:
{architecture[:4000]}

PRD Constraints:
{prd_content[:2000]}

Rules:
- PHP 5.6 compatible (no null coalescing ??, no spaceship <=>)
- MySQLi procedural functions ONLY (no PDO)
- Bootstrap 4 for frontend
- No frameworks (no Laravel, no CodeIgniter)
- Clean, well-commented code

Output format — for EACH file use exactly this format:
=== FILE: path/to/file.ext ===
<complete file content>
=== END FILE ==="""

            response = self.ai.code(prompt, context=context)
            return self._parse_code_response(response)

        except Exception as e:
            self.logger.error(f"Code generation failed: {e}")
            return None

    def _parse_json_response(self, response):
        """Extract JSON array from AI response."""
        # Try to find JSON in the response
        text = response.strip()

        # Remove markdown code fences if present
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()

        # Find the JSON array
        start = text.find('[')
        end = text.rfind(']') + 1

        if start == -1 or end == 0:
            self.logger.error("No JSON array found in response")
            return None

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            return None

    def _parse_code_response(self, response):
        """Parse AI response into file→content dict."""
        changes = {}
        lines = response.split('\n')
        current_file = None
        current_content = []

        for line in lines:
            if line.strip().startswith('=== FILE:'):
                current_file = line.split('FILE:')[1].split('===')[0].strip()
                current_content = []
            elif line.strip() == '=== END FILE ===' and current_file:
                changes[current_file] = '\n'.join(current_content)
                current_file = None
                current_content = []
            elif current_file is not None:
                current_content.append(line)

        return changes if changes else None
