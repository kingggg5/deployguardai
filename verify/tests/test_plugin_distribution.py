from __future__ import annotations

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_plugin_manifest_exposes_only_the_change_safety_skill() -> None:
    manifest = _load_json(ROOT / ".codex-plugin" / "plugin.json")
    project = tomllib.loads((ROOT / "verify" / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["name"] == "deployguardai"
    assert manifest["version"] == project["project"]["version"]
    assert manifest["skills"] == "./skills/"
    assert "ui-ux-pro-max-skill" not in json.dumps(manifest)


def test_marketplace_uses_the_public_repository_and_complete_policy() -> None:
    marketplace = _load_json(ROOT / ".agents" / "plugins" / "marketplace.json")
    plugins = marketplace["plugins"]
    assert isinstance(plugins, list) and len(plugins) == 1
    plugin = plugins[0]

    assert plugin["name"] == "deployguardai"
    assert plugin["source"] == {
        "source": "url",
        "url": "https://github.com/kingggg5/deployguardai.git",
        "ref": "main",
    }
    assert plugin["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert plugin["category"] == "Developer Tools"


def test_skill_resources_and_readme_install_contract_are_present() -> None:
    skill_root = ROOT / "skills" / "deployguard-change-safety"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert (skill_root / "agents" / "openai.yaml").is_file()
    assert (skill_root / "references" / "evidence-contract.md").is_file()
    assert "never infer or rewrite a decision from prose" in skill
    assert "codex plugin marketplace add kingggg5/deployguardai" in readme
    assert "Use $deployguard-change-safety" in readme
