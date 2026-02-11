# 📄 Product Requirements Document (PRD)

## Product Name

**AIDEV-OPS-Server** — Remote Autonomous AI Development System (API-Only)

---

## 1. Purpose & Vision

AIDEV-OPS-Server is a self-hosted autonomous software development system running on a dedicated Linux server that:

* Operates continuously (24/7)
* Is controlled remotely via VS Code over SSH
* Uses only free-tier AI APIs (no local models)
* Automatically manages per-project Docker environments
* Implements phase-based development
* Processes GitHub Issues autonomously
* Pushes validated code to GitHub

The system prioritizes **stability, cost efficiency, and remote-first operation**.

---

## 2. Operating Model

### Control Interface

* VS Code Remote SSH
* Server CLI
* Config files

### Execution Model

```
Developer (VS Code SSH)
        ↓
   Linux Server
        ↓
  AIDEV Controller
        ↓
 Docker Containers
        ↓
    GitHub
```

System runs as a background service.

---

## 3. Key Objectives

| ID | Objective                     |
| -- | ----------------------------- |
| O1 | 24/7 unattended execution     |
| O2 | Zero local LLM dependency     |
| O3 | Remote management via SSH     |
| O4 | Automatic container lifecycle |
| O5 | Free-tier API optimization    |
| O6 | Safe autonomous commits       |

---

## 4. Functional Requirements

---

## 4.1 System Bootstrap

### FR-1.1

System shall be installed on a dedicated Linux server.

### FR-1.2

System shall be controllable via SSH and VS Code.

### FR-1.3

System shall run as a systemd service.

### FR-1.4

System shall validate environment on startup.

---

## 4.2 Project Management

### FR-2.1

System shall create isolated project directories.

```
/opt/aidev/projects/<project-name>/
```

### FR-2.2

System shall auto-link projects to GitHub repositories.

### FR-2.3

System shall manage project states:

* idle
* building
* testing
* deployed
* blocked

---

## 4.3 Docker Automation

### FR-3.1

Each project shall run in its own Docker container.

### FR-3.2

Containers shall be created automatically.

### FR-3.3

Default base image:

```
ubuntu:22.04
```

### FR-3.4

Each container shall include:

* Apache
* PHP 5.6 support
* MySQL
* Git
* Python runtime

### FR-3.5

Containers shall be resource-limited.

---

## 4.4 AI Provider Routing (API-Only)

### FR-4.1

System shall support multiple free API providers.

### FR-4.2

System shall implement unified AI gateway.

### FR-4.3

System shall route tasks based on role.

### FR-4.4

System shall auto-failover on quota limits.

---

### Supported Providers (Initial)

| Provider   | Models                 |
| ---------- | ---------------------- |
| NVIDIA API | Qwen / Kimi / DeepSeek |
| Kilo Code  | Grok / Kimi            |
| Others     | Plugin-based           |

---

## 4.5 AI Role Architecture

| Role      | Function        | Model Type   |
| --------- | --------------- | ------------ |
| Planner   | Task breakdown  | Reasoning    |
| Architect | System design   | Long context |
| Coder     | Code generation | Coding       |
| Reviewer  | Validation      | Fast         |

Each role may use different providers.

---

## 4.6 Development Workflow

### FR-5.1

System shall pull latest code before execution.

### FR-5.2

System shall generate patches instead of full rewrites.

### FR-5.3

System shall enforce technical constraints:

* PHP 5.6 compatibility
* MySQLi procedural
* Bootstrap 4 frontend

### FR-5.4

System shall run automated tests.

### FR-5.5

System shall block unsafe changes.

---

## 4.7 GitHub Integration

### FR-6.1

System shall authenticate using PAT tokens.

### FR-6.2

System shall sync with remote branches.

### FR-6.3

System shall auto-commit and push.

### FR-6.4

System shall tag releases per phase.

---

## 4.8 Issue-Driven Automation

### FR-7.1

System shall poll GitHub Issues every 5 minutes.

### FR-7.2

System shall parse issue metadata.

### FR-7.3

System shall resolve issues automatically.

### FR-7.4

System shall close resolved issues.

---

## 4.9 Validation & Safety

### FR-8.1

All code must pass review agent.

### FR-8.2

System shall block:

* Destructive SQL
* Hardcoded secrets
* Unsafe shell commands

### FR-8.3

Manual override shall be supported.

---

## 4.10 Logging & Auditing

### FR-9.1

All activity shall be logged.

### FR-9.2

Logs stored under:

```
/opt/aidev/logs/
```

### FR-9.3

Each project has separate logs.

---

## 5. Non-Functional Requirements

---

### 5.1 Performance

| Metric          | Target |
| --------------- | ------ |
| Container Start | < 120s |
| Issue Fix Cycle | < 12h  |
| Cold Start      | < 45s  |

---

### 5.2 Reliability

* Auto-restart on crash
* Persistent state
* Checkpoint recovery

---

### 5.3 Security

* Encrypted API keys
* Non-root execution
* Network isolation
* Firewall rules

---

### 5.4 Cost Policy

* Free-tier only
* Quota-aware throttling
* Automatic downgrade

---

## 6. System Architecture

---

### 6.1 Core Modules

| Module          | Responsibility  |
| --------------- | --------------- |
| Agent Core      | Orchestration   |
| Project Manager | Lifecycle       |
| Docker Engine   | Container mgmt  |
| AI Gateway      | API routing     |
| Git Agent       | Version control |
| Issue Agent     | Issue mgmt      |
| Review Agent    | Validation      |
| Logger          | Auditing        |

---

## 6.2 Data Flow

```
VS Code (SSH)
     ↓
 Agent Core
     ↓
 Docker Runner
     ↓
 AI Gateway
     ↓
 GitHub
```

---

## 7. Configuration

### 7.1 config.yaml

```yaml
server:
  mode: production
  port: 9000

ai:
  strategy: api-only
  primary: nvidia
  fallback: kilo

docker:
  memory_limit: 1024m
  max_containers: 2

github:
  poll_interval: 300
```

---

## 8. Error Handling

| Condition    | Response        |
| ------------ | --------------- |
| API quota    | Switch provider |
| Docker crash | Rebuild         |
| Test failure | Rollback        |
| Push reject  | Rebase          |

---

## 9. Deployment & Operations

---

### 9.1 Installation Location

```
/opt/aidev/
```

---

### 9.2 Runtime

* systemd-managed service
* Background daemon

---

### 9.3 Control Commands

```bash
aidev start
aidev stop
aidev status
aidev logs
```

---

## 10. Acceptance Criteria

✔ Runs 24/7 on server
✔ Controlled via VS Code SSH
✔ Zero local models
✔ Auto container creation
✔ Issue → Fix → Push loop
✔ Survives reboot
✔ Stable ≥ 72 hours

---

## 11. Risks

| Risk             | Mitigation     |
| ---------------- | -------------- |
| Free API revoked | Multi-provider |
| RAM exhaustion   | Hard limits    |
| Bad commits      | Multi-review   |
| Network outage   | Queue tasks    |

---

## 12. Future Enhancements

* Web dashboard
* Team access
* Multi-server sync
* Self-optimization

---

## 13. Constraints & Assumptions

* Server has stable internet
* GitHub available
* APIs remain accessible
* User reviews periodically
