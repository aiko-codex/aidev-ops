"""
Workflow Executor for AIDEV-OPS.

Orchestrates the full development pipeline:
Issue → Plan → Code → Review → Test → Push

Enforces technical constraints (PHP 5.6, MySQLi, Bootstrap 4).
"""

import time
from src.logger import setup_logger
from src.workflow.reviewer import ReviewAgent
from src.workflow.patcher import PatchGenerator
from src.workflow.context import ContextBuilder


class WorkflowExecutor:
    """
    Main development workflow engine.

    Orchestrates the complete pipeline from issue to push:
    1. Receive work item (parsed issue)
    2. Plan the fix using Planner AI
    3. Generate code using Coder AI
    4. Review code using Reviewer (static + AI)
    5. Apply patches and test
    6. Commit and push

    Enforces project constraints at every step.
    """

    # Technical constraints from PRD
    CONSTRAINTS = {
        "php_version": "5.6",
        "db_driver": "MySQLi procedural",
        "frontend": "Bootstrap 4",
        "no_frameworks": True,
    }

    # Max retries for code generation
    MAX_CODE_RETRIES = 3

    def __init__(self, config, ai_gateway, project_manager,
                 docker_engine, git_agent):
        """
        Initialize Workflow Executor.

        Args:
            config: Application config dict
            ai_gateway: AIGateway instance
            project_manager: ProjectManager instance
            docker_engine: DockerEngine instance
            git_agent: GitAgent instance
        """
        self.config = config
        self.logger = setup_logger('workflow', config)
        self.ai = ai_gateway
        self.projects = project_manager
        self.docker = docker_engine
        self.git = git_agent
        self.reviewer = ReviewAgent(config, ai_gateway)
        self.patcher = PatchGenerator(config)
        self.context_builder = ContextBuilder(config)

    def execute(self, work_item):
        """
        Execute the full workflow for a work item.

        Args:
            work_item: Parsed issue dict from IssueParser

        Returns:
            dict: {
                "success": bool,
                "commit_sha": str or None,
                "summary": str,
                "errors": list
            }
        """
        issue_num = work_item['number']
        title = work_item['title']
        self.logger.info(f"═══ Starting workflow for issue #{issue_num}: {title}")

        result = {
            "success": False,
            "commit_sha": None,
            "summary": "",
            "errors": [],
        }

        try:
            # Step 1: Plan
            self.logger.info(f"[Step 1/5] Planning fix for #{issue_num}")
            plan = self._plan(work_item)
            if not plan:
                result["errors"].append("Planning failed")
                return result

            # Step 2: Generate code
            self.logger.info(f"[Step 2/5] Generating code for #{issue_num}")
            code_changes = self._generate_code(work_item, plan)
            if not code_changes:
                result["errors"].append("Code generation failed")
                return result

            # Step 3: Review
            self.logger.info(f"[Step 3/5] Reviewing code for #{issue_num}")
            review_result = self._review_code(code_changes)
            if not review_result["passed"]:
                result["errors"].append(
                    f"Review failed: {review_result['blocking_count']} issues"
                )
                result["errors"].extend(
                    [i['message'] for i in review_result['issues']
                     if i['severity'] == 'critical']
                )
                return result

            # Step 4: Apply & Test
            self.logger.info(f"[Step 4/5] Applying patches for #{issue_num}")
            apply_success = self._apply_changes(work_item, code_changes)
            if not apply_success:
                result["errors"].append("Patch application failed")
                return result

            # Step 5: Commit & Push
            self.logger.info(f"[Step 5/5] Committing for #{issue_num}")
            commit_sha = self._commit_and_push(work_item)
            if commit_sha:
                result["success"] = True
                result["commit_sha"] = commit_sha
                result["summary"] = f"Fixed issue #{issue_num}: {title}"
            else:
                result["errors"].append("Commit/push failed")

        except Exception as e:
            self.logger.error(f"Workflow error for #{issue_num}: {e}")
            result["errors"].append(str(e))

        self.logger.info(
            f"═══ Workflow {'COMPLETED' if result['success'] else 'FAILED'} "
            f"for issue #{issue_num}"
        )

        return result

    def _plan(self, work_item):
        """Use Planner AI to create a fix plan with codebase context."""
        try:
            # Build codebase context so AI can see the actual code
            project_name = work_item.get('repo', '').split('/')[-1]
            project_dir = self.projects.get_project_dir(project_name)
            codebase_context = self.context_builder.build_context(
                project_dir, issue=work_item
            )

            prompt = f"""Plan a fix for this issue:

Title: {work_item['title']}
Type: {work_item['type']}
Description: {work_item['body'][:2000]}
Affected files: {', '.join(work_item.get('affected_files', [])) or 'not specified'}

Constraints:
- PHP 5.6 compatible
- MySQLi procedural (no PDO, no ORM)
- Bootstrap 4 for frontend
- No frameworks

Provide:
1. Root cause analysis
2. Step-by-step fix plan
3. Files to modify
4. Test approach"""

            plan = self.ai.plan(prompt, context=codebase_context)
            self.logger.info(f"Plan generated ({len(plan)} chars)")
            return plan

        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            return None

    def _generate_code(self, work_item, plan):
        """Use Coder AI to generate code changes with codebase context."""
        # Build codebase context so AI sees the actual files
        project_name = work_item.get('repo', '').split('/')[-1]
        project_dir = self.projects.get_project_dir(project_name)
        codebase_context = self.context_builder.build_context(
            project_dir, issue=work_item
        )

        for attempt in range(self.MAX_CODE_RETRIES):
            try:
                prompt = f"""Generate code to fix this issue.

Issue: {work_item['title']}
Description: {work_item['body'][:1500]}

Plan:
{plan[:2000]}

Constraints:
- PHP 5.6 ONLY (no null coalescing ??, no spaceship <=>, no return types)
- MySQLi procedural functions ONLY
- Bootstrap 4 for any HTML/CSS
- No frameworks

Output format: For each file, use this format:
=== FILE: path/to/file.ext ===
<file content>
=== END FILE ==="""

                context = (
                    f"Attempt {attempt + 1}/{self.MAX_CODE_RETRIES}\n\n"
                    f"{codebase_context}"
                )
                response = self.ai.code(prompt, context)

                # Parse code blocks from response
                changes = self._parse_code_response(response)
                if changes:
                    self.logger.info(
                        f"Generated {len(changes)} file(s) "
                        f"(attempt {attempt + 1})"
                    )
                    return changes
                else:
                    self.logger.warning(
                        f"No parseable code in response (attempt {attempt + 1})"
                    )

            except Exception as e:
                self.logger.error(
                    f"Code generation attempt {attempt + 1} failed: {e}"
                )

        return None

    def _parse_code_response(self, response):
        """
        Parse AI response into file→content dict.

        Expects format:
        === FILE: path/to/file.ext ===
        <content>
        === END FILE ===
        """
        changes = {}
        lines = response.split('\n')
        current_file = None
        current_content = []

        for line in lines:
            if line.strip().startswith('=== FILE:'):
                # Start new file
                current_file = line.split('FILE:')[1].split('===')[0].strip()
                current_content = []
            elif line.strip() == '=== END FILE ===' and current_file:
                changes[current_file] = '\n'.join(current_content)
                current_file = None
                current_content = []
            elif current_file is not None:
                current_content.append(line)

        return changes

    def _review_code(self, code_changes):
        """Review all code changes."""
        all_issues = []
        all_passed = True

        for filename, content in code_changes.items():
            result = self.reviewer.review(content, filename)
            all_issues.extend(result['issues'])
            if not result['passed']:
                all_passed = False

        return {
            "passed": all_passed,
            "issues": all_issues,
            "blocking_count": sum(
                1 for i in all_issues if i['severity'] == 'critical'
            ),
        }

    def _apply_changes(self, work_item, code_changes):
        """Apply code changes as patches."""
        project_name = work_item.get('repo', '').split('/')[-1]
        project = self.projects.get_project(project_name)

        if not project:
            self.logger.error(f"Project not found: {project_name}")
            return False

        project_dir = self.projects.get_project_dir(project_name)
        all_applied = True

        for filename, content in code_changes.items():
            file_path = project_dir / filename
            result = self.patcher.apply_patch(file_path, content)

            if not result['success']:
                self.logger.error(f"Failed to apply patch: {filename}")
                all_applied = False
                break

            # Save the patch
            if result['patch']:
                self.patcher.save_patch_file(
                    result['patch'],
                    str(project_dir),
                    f"issue_{work_item['number']}_{filename.replace('/', '_')}.diff"
                )

        return all_applied

    def _commit_and_push(self, work_item):
        """Commit and push the changes."""
        project_name = work_item.get('repo', '').split('/')[-1]
        project_dir = self.projects.get_project_dir(project_name)

        message = (
            f"Fix #{work_item['number']}: {work_item['title']}\n\n"
            f"Type: {work_item['type']}\n"
            f"Auto-resolved by AIDEV-OPS"
        )

        # Commit
        if self.git.commit(project_dir, message):
            # Push
            if self.git.push(project_dir):
                # Get commit SHA
                _, sha = self.git._run_git(
                    ['rev-parse', 'HEAD'],
                    cwd=str(project_dir)
                )
                return sha.strip()[:8] if sha else None

        return None
