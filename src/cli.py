"""
CLI Interface for AIDEV-OPS.

Provides the `aidev` command-line interface:
  aidev start    — Start the daemon
  aidev stop     — Stop the daemon
  aidev status   — Show system status
  aidev logs     — Tail log files
  aidev project  — Manage projects
  aidev ai       — Test AI gateway
"""

import os
import sys
import json
import time
import signal
import click
from pathlib import Path
from src.config import load_config
from src.logger import setup_logger


@click.group()
@click.pass_context
def cli(ctx):
    """AIDEV-OPS — Autonomous AI Development System"""
    ctx.ensure_object(dict)
    try:
        ctx.obj['config'] = load_config()
    except Exception as e:
        click.echo(f"⚠ Config error: {e}", err=True)
        ctx.obj['config'] = {}


# ──────────────────────────────────────────────
# Start / Stop / Status
# ──────────────────────────────────────────────

@cli.command()
@click.option('--foreground', '-f', is_flag=True, help='Run in foreground')
@click.pass_context
def start(ctx, foreground):
    """Start the AIDEV-OPS daemon."""
    config = ctx.obj['config']

    click.echo("🚀 Starting AIDEV-OPS...")
    click.echo(f"   Mode: {config.get('server', {}).get('mode', 'unknown')}")

    from src.core import AgentCore

    agent = AgentCore(config)

    if foreground:
        click.echo("   Running in foreground (Ctrl+C to stop)")
        agent.start()
    else:
        click.echo("   Starting as background process...")
        # For true daemon mode on Linux, use systemd
        agent.start()


@cli.command()
@click.pass_context
def stop(ctx):
    """Stop the AIDEV-OPS daemon."""
    config = ctx.obj['config']
    pid_file = config.get('server', {}).get('pid_file', '/opt/aidev/aidev.pid')

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        os.kill(pid, signal.SIGTERM)
        click.echo(f"✅ Sent stop signal to PID {pid}")

        # Wait for shutdown
        for _ in range(10):
            try:
                os.kill(pid, 0)  # Check if still running
                time.sleep(1)
            except OSError:
                click.echo("   Process stopped")
                return

        click.echo("   ⚠ Process may still be running")

    except FileNotFoundError:
        click.echo("ℹ  No PID file found — daemon may not be running")
    except ProcessLookupError:
        click.echo("ℹ  Process not found — daemon already stopped")
        Path(pid_file).unlink(missing_ok=True)
    except Exception as e:
        click.echo(f"⚠ Error: {e}")


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    config = ctx.obj['config']

    click.echo("═══════════════════════════════════════")
    click.echo("  AIDEV-OPS System Status")
    click.echo("═══════════════════════════════════════")

    # Check if daemon is running
    pid_file = config.get('server', {}).get('pid_file', '/opt/aidev/aidev.pid')
    running = False
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        running = True
        click.echo(f"  Daemon:   ✅ Running (PID {pid})")
    except Exception:
        click.echo(f"  Daemon:   ❌ Not running")

    # Config info
    click.echo(f"  Mode:     {config.get('server', {}).get('mode', 'unknown')}")

    # AI Gateway
    ai_config = config.get('ai', {})
    nvidia = ai_config.get('providers', {}).get('nvidia', {})
    keys = nvidia.get('api_keys', [])
    valid_keys = [k for k in keys if k and len(k) > 10]
    click.echo(f"  AI Keys:  {len(valid_keys)} configured")

    # Roles
    roles = ai_config.get('roles', {})
    click.echo(f"  AI Roles: {', '.join(roles.keys())}")

    for role_name, role_conf in roles.items():
        click.echo(f"    • {role_name}: {role_conf.get('model', 'not set')}")

    # Docker
    try:
        from src.docker_engine.engine import DockerEngine
        docker = DockerEngine(config)
        docker_status = "✅ Available" if docker.is_available() else "❌ Unavailable"
    except Exception:
        docker_status = "❌ Not installed"
    click.echo(f"  Docker:   {docker_status}")

    # Projects
    try:
        from src.project.manager import ProjectManager
        pm = ProjectManager(config)
        click.echo(f"  Projects: {pm.project_count}")
        for p in pm.list_projects():
            click.echo(f"    • {p['name']} [{p['status']}]")
    except Exception:
        click.echo(f"  Projects: 0")

    click.echo("═══════════════════════════════════════")


# ──────────────────────────────────────────────
# Log viewing
# ──────────────────────────────────────────────

@cli.command()
@click.option('--lines', '-n', default=50, help='Number of lines to show')
@click.option('--module', '-m', default=None, help='Filter by module name')
@click.pass_context
def logs(ctx, lines, module):
    """View system logs."""
    config = ctx.obj['config']
    log_dir = Path(config.get('logging', {}).get('dir', '/opt/aidev/logs'))

    if not log_dir.exists():
        click.echo("ℹ  No logs found")
        return

    # Find log files
    log_files = list(log_dir.glob("*.log"))
    if module:
        log_files = [f for f in log_files if module in f.name]

    if not log_files:
        click.echo(f"ℹ  No log files found" + (f" for module '{module}'" if module else ""))
        return

    for log_file in sorted(log_files):
        click.echo(f"\n── {log_file.name} ──")
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    click.echo(line.rstrip())
        except Exception as e:
            click.echo(f"  Error reading: {e}")


# ──────────────────────────────────────────────
# Project management
# ──────────────────────────────────────────────

@cli.group()
@click.pass_context
def project(ctx):
    """Manage projects."""
    pass


@project.command('add')
@click.argument('name')
@click.option('--repo', '-r', default='', help='GitHub repository URL')
@click.option('--branch', '-b', default='main', help='Default branch')
@click.pass_context
def project_add(ctx, name, repo, branch):
    """Add a new project."""
    config = ctx.obj['config']

    from src.project.manager import ProjectManager
    pm = ProjectManager(config)

    try:
        project = pm.create_project(name, repo, branch)
        click.echo(f"✅ Project created: {name}")
        click.echo(f"   Repo: {repo or 'not set'}")
        click.echo(f"   Branch: {branch}")

        # Clone if repo provided
        if repo:
            from src.git.agent import GitAgent
            git = GitAgent(config)
            project_dir = pm.get_project_dir(name)
            if git.clone(repo, project_dir, branch):
                click.echo(f"   ✅ Repository cloned")
            else:
                click.echo(f"   ⚠ Clone failed — set up manually")

    except ValueError as e:
        click.echo(f"⚠ {e}")


@project.command('list')
@click.pass_context
def project_list(ctx):
    """List all projects."""
    config = ctx.obj['config']

    from src.project.manager import ProjectManager
    pm = ProjectManager(config)

    projects = pm.list_projects()
    if not projects:
        click.echo("ℹ  No projects configured")
        return

    click.echo(f"\n{'Name':<20} {'Status':<12} {'Last Activity'}")
    click.echo("─" * 55)
    for p in projects:
        click.echo(f"{p['name']:<20} {p['status']:<12} {p['last_activity']}")


@project.command('remove')
@click.argument('name')
@click.confirmation_option(prompt='Are you sure?')
@click.pass_context
def project_remove(ctx, name):
    """Remove a project (state only)."""
    config = ctx.obj['config']

    from src.project.manager import ProjectManager
    pm = ProjectManager(config)
    pm.delete_project(name)
    click.echo(f"✅ Project removed: {name}")


# ──────────────────────────────────────────────
# AI testing
# ──────────────────────────────────────────────

@cli.group()
@click.pass_context
def ai(ctx):
    """AI gateway operations."""
    pass


@ai.command('test')
@click.option('--role', '-r', default='reviewer',
              type=click.Choice(['planner', 'architect', 'coder', 'reviewer']))
@click.option('--prompt', '-p', default='Say hello and confirm you are working.',
              help='Test prompt')
@click.pass_context
def ai_test(ctx, role, prompt):
    """Test AI gateway with a role."""
    config = ctx.obj['config']

    click.echo(f"🤖 Testing AI Gateway (role: {role})...")

    from src.ai.gateway import AIGateway
    gateway = AIGateway(config)

    try:
        response = gateway.chat(role, prompt)
        click.echo(f"\n✅ Response ({len(response)} chars):\n")
        click.echo(response[:500])
        if len(response) > 500:
            click.echo(f"\n... ({len(response) - 500} more chars)")
    except Exception as e:
        click.echo(f"\n❌ Error: {e}")


@ai.command('health')
@click.pass_context
def ai_health(ctx):
    """Check AI provider health."""
    config = ctx.obj['config']

    click.echo("🏥 Checking AI provider health...")

    from src.ai.gateway import AIGateway
    gateway = AIGateway(config)

    results = gateway.health_check()
    for name, result in results.items():
        status_icon = "✅" if result['status'] == 'healthy' else "❌"
        click.echo(f"  {status_icon} {name}: {result['status']}")
        if result.get('error'):
            click.echo(f"     Error: {result['error']}")


@ai.command('stats')
@click.pass_context
def ai_stats(ctx):
    """Show AI gateway stats."""
    config = ctx.obj['config']

    from src.ai.gateway import AIGateway
    gateway = AIGateway(config)

    stats = gateway.stats
    click.echo(f"\n  Providers: {stats['total_providers']}")
    for p in stats['providers']:
        click.echo(f"  • Key {p['key_suffix']}: {p['requests']} requests, {p['errors']} errors")


def main():
    """Entry point for the CLI."""
    cli(obj={})
