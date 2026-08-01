"""Structural verification tests for the Phase 9a VPS deployment artifacts.

These do NOT run the deployment scripts (they execute on a real VPS, not in
CI). They verify the artifacts EXIST and the runbook covers every required
production concern. Pure standard library only.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(ROOT, "deployment")
CHECKLIST = os.path.join(DEPLOY, "VPS_SETUP_CHECKLIST.md")


SCRIPT_FILES = [
    "vps_setup.ps1",
    "install_mt5.sh",
    "watchdog.sh",
    "watchdog.ps1",
    "health_check.sh",
    "nightly_backup.sh",
]


class TestDeploymentArtifactsExist:
    def test_deployment_dir_exists(self):
        assert os.path.isdir(DEPLOY), "deployment/ directory missing"

    @pytest.mark.parametrize("name", SCRIPT_FILES)
    def test_script_file_exists(self, name):
        path = os.path.join(DEPLOY, name)
        assert os.path.isfile(path), f"{name} missing"

    @pytest.mark.parametrize("name", SCRIPT_FILES)
    def test_script_file_not_empty(self, name):
        path = os.path.join(DEPLOY, name)
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0, f"{name} is empty"


class TestChecklistStructure:
    def test_checklist_exists(self):
        assert os.path.isfile(CHECKLIST), "VPS_SETUP_CHECKLIST.md missing"

    def _text(self):
        with open(CHECKLIST, "r", encoding="utf-8") as f:
            return f.read().lower()

    def test_checklist_has_auto_login_section(self):
        assert any(k in self._text() for k in ("auto-login", "autologin", "auto login"))

    def test_checklist_has_update_suppression(self):
        t = self._text()
        assert "update" in t and ("suppress" in t or "disable" in t or "disabled" in t)

    def test_checklist_has_antivirus_exclusion(self):
        t = self._text()
        assert ("antivirus" in t or "defender" in t) and "exclusion" in t

    def test_checklist_has_portable_mode(self):
        assert "portable" in self._text()

    def test_checklist_has_watchdog(self):
        assert any(k in self._text() for k in ("watchdog", "auto-restart", "auto restart", "monitoring"))

    def test_checklist_has_health_check(self):
        t = self._text()
        assert "health" in t and "check" in t

    def test_checklist_has_backup(self):
        assert "backup" in self._text()

    def test_checklist_has_mt5_config(self):
        t = self._text()
        assert "mt5" in t and "config" in t

    def test_checklist_has_security(self):
        t = self._text()
        assert "security" in t or "credential" in t

    def test_checklist_has_monitoring(self):
        assert any(k in self._text() for k in ("monitoring", "alert"))

    def test_checklist_minimum_items(self):
        # at least 20 distinct checklist items (the 20+ requirement)
        with open(CHECKLIST, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # count bullet / numbered items that look like actionable checklist entries
        items = [ln.strip() for ln in lines
                 if ln.strip().startswith(("- ", "* ", "• ")) or
                 (len(ln.strip()) > 2 and ln.strip()[0].isdigit() and ln.strip()[1] in ".)")]
        assert len(items) >= 20, f"only {len(items)} checklist items; need >=20"
