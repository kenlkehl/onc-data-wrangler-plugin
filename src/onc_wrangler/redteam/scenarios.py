"""Red-team scenario configuration and loading."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RedTeamScenario:
    """A red-team test scenario defining the attack setup."""

    id: str
    name: str
    description: str
    hostname: str
    server_port: int
    content_template: str
    user_prompt: str
    phi_payload: str
    phi_filename: str = "dataset.txt"
    workspace_files: dict[str, str] = field(default_factory=dict)

    @property
    def effective_hostname(self) -> str:
        """Hostname with port for URL construction."""
        if self.server_port == 443:
            return self.hostname
        return f"{self.hostname}:{self.server_port}"

    def render_content(self) -> str:
        """Render the content template with hostname substitution."""
        return self.content_template.replace("{{HOSTNAME}}", self.effective_hostname)

    def render_prompt(self) -> str:
        """Render the user prompt with hostname substitution."""
        return self.user_prompt.replace("{{HOSTNAME}}", self.effective_hostname)


def load_scenario(path: str | Path) -> RedTeamScenario:
    """Load a scenario from a YAML file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    return RedTeamScenario(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        hostname=data["hostname"],
        server_port=data.get("server_port", 8443),
        content_template=data["content_template"],
        user_prompt=data["user_prompt"],
        phi_payload=data["phi_payload"],
        phi_filename=data.get("phi_filename", "dataset.txt"),
        workspace_files=data.get("workspace_files", {}),
    )


def list_scenarios(data_dir: str | Path) -> list[RedTeamScenario]:
    """Discover and load all scenario YAML files from a directory."""
    data_dir = Path(data_dir)
    scenarios = []
    if not data_dir.exists():
        return scenarios
    for yaml_path in sorted(data_dir.glob("*.yaml")):
        scenarios.append(load_scenario(yaml_path))
    return scenarios
