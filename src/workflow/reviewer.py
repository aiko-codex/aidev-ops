"""
Code Reviewer for AIDEV-OPS.

Validates code changes for safety, quality, and constraint compliance.
Blocks destructive SQL, hardcoded secrets, and unsafe shell commands.
"""

import re
from src.logger import setup_logger


class ReviewAgent:
    """
    Automated code review agent.

    Performs two levels of review:
    1. Static analysis: Pattern-based checks for common issues
    2. AI review: Uses the Reviewer AI role for deeper analysis

    Blocks unsafe changes before they reach production.
    """

    # Dangerous SQL patterns
    DANGEROUS_SQL = [
        re.compile(r'\bDROP\s+(TABLE|DATABASE)\b', re.IGNORECASE),
        re.compile(r'\bTRUNCATE\s+TABLE\b', re.IGNORECASE),
        re.compile(r'\bDELETE\s+FROM\s+\w+\s*$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'\bALTER\s+TABLE\s+\w+\s+DROP\b', re.IGNORECASE),
    ]

    # Secret patterns (API keys, passwords, tokens)
    SECRET_PATTERNS = [
        re.compile(r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
        re.compile(r'(?:api_key|apikey|api_secret)\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
        re.compile(r'(?:token|secret)\s*=\s*["\'][^"\']{16,}["\']', re.IGNORECASE),
        re.compile(r'nvapi-[a-zA-Z0-9_-]{20,}'),  # NVIDIA API keys
        re.compile(r'ghp_[a-zA-Z0-9]{36,}'),  # GitHub PAT
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),  # OpenAI keys
    ]

    # Unsafe shell patterns
    UNSAFE_SHELL = [
        re.compile(r'\brm\s+-rf\s+/', re.IGNORECASE),
        re.compile(r'\bchmod\s+777\b'),
        re.compile(r'\bcurl\s+.*\|\s*(?:bash|sh)\b', re.IGNORECASE),
        re.compile(r'\bwget\s+.*\|\s*(?:bash|sh)\b', re.IGNORECASE),
        re.compile(r'\beval\s*\(', re.IGNORECASE),
        re.compile(r'\bexec\s*\(', re.IGNORECASE),
    ]

    # PHP 5.6 incompatible patterns
    PHP56_INCOMPATIBLE = [
        re.compile(r'\?\?'),  # Null coalescing (PHP 7.0+)
        re.compile(r'<=>\s'),  # Spaceship operator (PHP 7.0+)
        re.compile(r'\bfunction\s*\([^)]*\)\s*:\s*\w+'),  # Return type declarations (PHP 7.0+)
        re.compile(r'\byield\s+from\b', re.IGNORECASE),  # Generator delegation (PHP 7.0+)
    ]

    def __init__(self, config, ai_gateway=None):
        """
        Initialize Review Agent.

        Args:
            config: Application config dict
            ai_gateway: Optional AIGateway for AI-powered review
        """
        self.config = config
        self.logger = setup_logger('reviewer', config)
        self.ai_gateway = ai_gateway

    def review(self, code, filename="", context=""):
        """
        Review code for safety and quality.

        Args:
            code: Code string to review
            filename: Filename for context
            context: Additional context (issue description, etc.)

        Returns:
            dict: {
                "passed": bool,
                "issues": list of issue dicts,
                "ai_review": str (if AI review enabled)
            }
        """
        self.logger.info(f"Reviewing: {filename or 'inline code'}")

        issues = []

        # 1. Static analysis
        issues.extend(self._check_dangerous_sql(code))
        issues.extend(self._check_secrets(code))
        issues.extend(self._check_unsafe_shell(code))

        # Check PHP-specific issues if it's a PHP file
        if filename.endswith('.php'):
            issues.extend(self._check_php56_compat(code))

        # 2. AI-powered review (if gateway available)
        ai_review = ""
        if self.ai_gateway and not issues:
            # Only do AI review if static checks pass
            ai_review = self._ai_review(code, filename, context)

        # Determine pass/fail
        blocking_issues = [i for i in issues if i['severity'] == 'critical']
        passed = len(blocking_issues) == 0

        result = {
            "passed": passed,
            "issues": issues,
            "issue_count": len(issues),
            "blocking_count": len(blocking_issues),
            "ai_review": ai_review,
        }

        if passed:
            self.logger.info(f"Review PASSED for {filename}")
        else:
            self.logger.warning(
                f"Review FAILED for {filename}: "
                f"{len(blocking_issues)} blocking issue(s)"
            )

        return result

    def _check_dangerous_sql(self, code):
        """Check for destructive SQL statements."""
        issues = []
        for pattern in self.DANGEROUS_SQL:
            matches = pattern.findall(code)
            if matches:
                issues.append({
                    "type": "dangerous_sql",
                    "severity": "critical",
                    "message": f"Destructive SQL detected: {matches[0]}",
                    "pattern": pattern.pattern,
                })
        return issues

    def _check_secrets(self, code):
        """Check for hardcoded secrets."""
        issues = []
        for pattern in self.SECRET_PATTERNS:
            matches = pattern.findall(code)
            if matches:
                # Mask the secret in the message
                masked = matches[0][:10] + "***"
                issues.append({
                    "type": "hardcoded_secret",
                    "severity": "critical",
                    "message": f"Possible hardcoded secret: {masked}",
                    "pattern": pattern.pattern,
                })
        return issues

    def _check_unsafe_shell(self, code):
        """Check for unsafe shell commands."""
        issues = []
        for pattern in self.UNSAFE_SHELL:
            matches = pattern.findall(code)
            if matches:
                issues.append({
                    "type": "unsafe_shell",
                    "severity": "critical",
                    "message": f"Unsafe shell command: {matches[0]}",
                    "pattern": pattern.pattern,
                })
        return issues

    def _check_php56_compat(self, code):
        """Check for PHP 5.6 incompatibilities."""
        issues = []
        for pattern in self.PHP56_INCOMPATIBLE:
            matches = pattern.findall(code)
            if matches:
                issues.append({
                    "type": "php56_incompatible",
                    "severity": "warning",
                    "message": f"PHP 5.6 incompatible syntax: {matches[0]}",
                    "pattern": pattern.pattern,
                })
        return issues

    def _ai_review(self, code, filename, context):
        """
        Perform AI-powered code review.

        Returns:
            str: AI review output
        """
        try:
            prompt = f"""Review this code for quality and safety.

Filename: {filename}
Context: {context}

Code:
```
{code[:4000]}
```

Check for:
1. Security vulnerabilities
2. Logic errors
3. Performance issues
4. Code quality

Respond with PASS or FAIL, followed by your analysis."""

            response = self.ai_gateway.review(prompt)
            return response

        except Exception as e:
            self.logger.warning(f"AI review failed: {e}")
            return f"AI review unavailable: {e}"
