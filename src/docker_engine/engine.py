"""
Docker Engine for AIDEV-OPS.

Manages per-project Docker containers with resource limits.
Creates containers from a base image (ubuntu:22.04) with
Apache, PHP, MySQL client, Git, and Python pre-installed.
"""

import docker
from docker.errors import DockerException, NotFound, APIError
from src.logger import setup_logger


class DockerEngine:
    """
    Docker container management for project isolation.

    Features:
    - Auto-create containers per project
    - Resource limits (memory, CPU) for low-RAM server
    - Container health checks
    - Rebuild on crash
    - Container exec for running commands
    """

    def __init__(self, config):
        """
        Initialize Docker Engine.

        Args:
            config: Application config dict
        """
        self.config = config
        self.logger = setup_logger('docker_engine', config)
        self.docker_config = config.get('docker', {})

        self.memory_limit = self.docker_config.get('memory_limit', '512m')
        self.cpu_limit = self.docker_config.get('cpu_limit', 1.0)
        self.max_containers = self.docker_config.get('max_containers', 2)
        self.base_image = self.docker_config.get('base_image', 'ubuntu:22.04')
        self.network_name = self.docker_config.get('network', 'aidev-net')

        # Initialize Docker client
        try:
            self.client = docker.from_env()
            self.logger.info("Docker client connected")
            self._ensure_network()
        except DockerException as e:
            self.logger.error(f"Docker not available: {e}")
            self.client = None

    def _ensure_network(self):
        """Create the aidev network if it doesn't exist."""
        try:
            self.client.networks.get(self.network_name)
        except NotFound:
            self.client.networks.create(self.network_name, driver="bridge")
            self.logger.info(f"Created network: {self.network_name}")

    def is_available(self):
        """Check if Docker is available."""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def create_container(self, project_name, project_dir):
        """
        Create a Docker container for a project.

        Args:
            project_name: Project name (used for container name)
            project_dir: Host path to project directory

        Returns:
            Container ID string

        Raises:
            RuntimeError: If max containers reached or Docker unavailable
        """
        if not self.is_available():
            raise RuntimeError("Docker is not available")

        # Check container limit
        running = self._get_aidev_containers()
        if len(running) >= self.max_containers:
            raise RuntimeError(
                f"Max container limit reached ({self.max_containers}). "
                f"Stop a container first."
            )

        container_name = f"aidev-{project_name}"

        # Remove existing container with same name
        self._remove_container(container_name)

        self.logger.info(
            f"Creating container '{container_name}' "
            f"(mem: {self.memory_limit}, cpu: {self.cpu_limit})"
        )

        try:
            container = self.client.containers.run(
                self.base_image,
                name=container_name,
                detach=True,
                mem_limit=self.memory_limit,
                nano_cpus=int(self.cpu_limit * 1e9),
                network=self.network_name,
                volumes={
                    str(project_dir): {
                        'bind': '/workspace',
                        'mode': 'rw'
                    }
                },
                working_dir='/workspace',
                command='tail -f /dev/null',  # Keep alive
                labels={'managed-by': 'aidev-ops'},
                restart_policy={'Name': 'unless-stopped'},
            )

            self.logger.info(
                f"Container created: {container.short_id} ({container_name})"
            )
            return container.id

        except APIError as e:
            self.logger.error(f"Failed to create container: {e}")
            raise RuntimeError(f"Container creation failed: {e}")

    def exec_command(self, container_id, command, workdir=None):
        """
        Execute a command inside a container.

        Args:
            container_id: Container ID or name
            command: Command string or list
            workdir: Working directory inside container

        Returns:
            tuple: (exit_code, output_string)
        """
        if not self.is_available():
            return (-1, "Docker not available")

        try:
            container = self.client.containers.get(container_id)

            if isinstance(command, str):
                command = ['sh', '-c', command]

            exec_kwargs = {'cmd': command, 'demux': True}
            if workdir:
                exec_kwargs['workdir'] = workdir

            exit_code, output = container.exec_run(**exec_kwargs)

            # Combine stdout and stderr
            if isinstance(output, tuple):
                stdout, stderr = output
                result = ""
                if stdout:
                    result += stdout.decode('utf-8', errors='replace')
                if stderr:
                    result += stderr.decode('utf-8', errors='replace')
            else:
                result = output.decode('utf-8', errors='replace') if output else ""

            return (exit_code, result)

        except NotFound:
            return (-1, f"Container {container_id} not found")
        except Exception as e:
            return (-1, f"Exec error: {e}")

    def stop_container(self, container_id, timeout=10):
        """Stop a container."""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            self.logger.info(f"Stopped container: {container.short_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop container: {e}")
            return False

    def remove_container(self, container_id, force=True):
        """Remove a container."""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            self.logger.info(f"Removed container: {container.short_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove container: {e}")
            return False

    def _remove_container(self, name):
        """Remove container by name if it exists."""
        try:
            container = self.client.containers.get(name)
            container.remove(force=True)
            self.logger.debug(f"Removed existing container: {name}")
        except NotFound:
            pass
        except Exception as e:
            self.logger.warning(f"Error removing container {name}: {e}")

    def rebuild_container(self, project_name, project_dir):
        """
        Rebuild a container (remove old, create new).

        Args:
            project_name: Project name
            project_dir: Host path to project directory

        Returns:
            New container ID
        """
        container_name = f"aidev-{project_name}"
        self._remove_container(container_name)
        return self.create_container(project_name, project_dir)

    def get_container_status(self, container_id):
        """
        Get container status info.

        Returns:
            dict with status details or None
        """
        try:
            container = self.client.containers.get(container_id)
            return {
                "id": container.short_id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else "unknown",
            }
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error getting container status: {e}")
            return None

    def _get_aidev_containers(self):
        """Get all containers managed by AIDEV-OPS."""
        try:
            return self.client.containers.list(
                filters={'label': 'managed-by=aidev-ops'}
            )
        except Exception:
            return []

    def list_containers(self):
        """List all AIDEV-OPS managed containers."""
        containers = self._get_aidev_containers()
        return [
            {
                "id": c.short_id,
                "name": c.name,
                "status": c.status,
            }
            for c in containers
        ]

    def cleanup_all(self):
        """Remove all AIDEV-OPS containers."""
        containers = self._get_aidev_containers()
        for c in containers:
            try:
                c.remove(force=True)
                self.logger.info(f"Cleaned up container: {c.name}")
            except Exception as e:
                self.logger.error(f"Cleanup failed for {c.name}: {e}")
