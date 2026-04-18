"""Tests for the R/Bioconductor backend integration (milestone M9/M10).

Run with:
    uv run --directory onc-data-wrangler-plugin pytest tests/test_r_backend.py -v
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from onc_wrangler.agent.tools import (
    ALL_TOOLS,
    DEFAULT_TOOLS,
    EXECUTE_R_SCHEMA,
    ToolCall,
    execute_r,
    execute_tool,
)


R_AVAILABLE = shutil.which("Rscript") is not None
PLUGIN_ROOT = Path(__file__).parent.parent
RECIPES_R = PLUGIN_ROOT / "skills" / "analyze-data" / "recipes" / "R"
RECIPES_SCANPY = PLUGIN_ROOT / "skills" / "analyze-data" / "recipes" / "scanpy"


class TestToolRegistry:
    def test_all_tools_contains_execute_r(self):
        names = {t.name for t in ALL_TOOLS}
        assert names == {"execute_python", "read_file", "list_files", "execute_r"}

    def test_default_tools_unchanged_for_backcompat(self):
        names = {t.name for t in DEFAULT_TOOLS}
        assert "execute_r" not in names
        assert names == {"execute_python", "read_file", "list_files"}

    def test_execute_r_schema_shape(self):
        assert EXECUTE_R_SCHEMA.name == "execute_r"
        assert "code" in EXECUTE_R_SCHEMA.parameters["properties"]
        assert EXECUTE_R_SCHEMA.parameters["required"] == ["code"]


class TestExecuteRFallback:
    """Behavior when Rscript is missing (skipped if R is actually installed)."""

    @pytest.mark.skipif(R_AVAILABLE, reason="Rscript is installed; skip missing-binary test")
    def test_returns_backend_unavailable_when_r_missing(self, tmp_path):
        out = execute_r('cat("hi\\n")', work_dir=str(tmp_path), timeout=5)
        assert "BACKEND_UNAVAILABLE" in out
        assert "R_INSTALL.md" in out

    @pytest.mark.skipif(R_AVAILABLE, reason="Rscript is installed; skip missing-binary test")
    def test_tool_dispatcher_reports_not_an_error_for_backend_unavailable(self, tmp_path):
        call = ToolCall(id="1", name="execute_r", arguments={"code": 'cat("hi\\n")'})
        result = execute_tool(call, work_dir=str(tmp_path), allowed_dirs=[str(tmp_path)])
        # BACKEND_UNAVAILABLE is a structured non-fatal signal; execute_tool marks
        # it as not-an-error so the worker can emit a clean result.
        assert "BACKEND_UNAVAILABLE" in result.content
        assert result.is_error is False


@pytest.mark.skipif(not R_AVAILABLE, reason="Rscript not installed -- integration tests require R")
class TestExecuteRIntegration:
    def test_hello_world(self, tmp_path):
        out = execute_r('cat("hello-R\\n")', work_dir=str(tmp_path), timeout=30)
        assert "hello-R" in out

    def test_captures_stderr_on_error(self, tmp_path):
        out = execute_r('stop("intentional-failure")', work_dir=str(tmp_path), timeout=30)
        assert "Exit code" in out
        assert "intentional-failure" in out

    def test_timeout_returns_structured_message(self, tmp_path):
        out = execute_r("Sys.sleep(30)", work_dir=str(tmp_path), timeout=2)
        assert "timed out" in out.lower()


class TestRRecipesSyntax:
    """Validate each shipped R recipe parses without executing it."""

    @pytest.mark.parametrize("recipe", [
        "idat_to_beta.R",
        "conumee_cnv.R",
        "limma_voom_de.R",
        "fgsea_c6.R",
        "consensus_cluster.R",
    ])
    @pytest.mark.skipif(not R_AVAILABLE, reason="Rscript not installed")
    def test_recipe_parses(self, recipe):
        path = RECIPES_R / recipe
        assert path.exists(), f"recipe missing: {path}"
        # parse() returns without executing; this catches syntax errors
        code = f'invisible(parse("{path}"))'
        result = subprocess.run(
            ["Rscript", "--vanilla", "-e", code],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"parse failure: {result.stderr}"

    @pytest.mark.parametrize("recipe", [
        "idat_to_beta.R",
        "conumee_cnv.R",
        "limma_voom_de.R",
        "fgsea_c6.R",
        "consensus_cluster.R",
    ])
    def test_recipe_header_documents_usage(self, recipe):
        text = (RECIPES_R / recipe).read_text()
        assert text.startswith("#!/usr/bin/env Rscript")
        assert "Usage:" in text.splitlines()[1]


class TestScanpyRecipesSyntax:
    """Validate each shipped scanpy recipe compiles."""

    @pytest.mark.parametrize("recipe", [
        "load_10x.py",
        "qc.py",
        "hvg_leiden.py",
        "celltypist_annotate.py",
        "infercnv.py",
    ])
    def test_recipe_compiles(self, recipe):
        import py_compile
        path = RECIPES_SCANPY / recipe
        assert path.exists(), f"recipe missing: {path}"
        py_compile.compile(str(path), doraise=True)

    def test_requirements_txt_lists_scanpy_and_infercnvpy(self):
        reqs = (RECIPES_SCANPY / "requirements.txt").read_text()
        assert "scanpy==" in reqs
        assert "infercnvpy==" in reqs
        assert "celltypist==" in reqs


class TestRenvLockScaffold:
    def test_lockfile_is_valid_json(self):
        data = json.loads((RECIPES_R / "renv.lock").read_text())
        assert data["Bioconductor"]["Version"] == "3.18"
        pkgs = data["Packages"]
        assert {"minfi", "conumee", "limma", "edgeR", "DESeq2",
                "fgsea", "ConsensusClusterPlus"}.issubset(pkgs.keys())


class TestBlindingContract:
    """Verify the collapsed wrapper agents do not reference paper/answers paths.

    Phase-2 `analysis-worker` must not read paper PDFs or `questions_with_answers.xlsx`
    -- the wrapper is the enforcement boundary. This test inspects the agent
    definition text to catch regressions.
    """

    def test_analysis_worker_wrapper_contains_no_paper_references(self):
        text = (PLUGIN_ROOT / "agents" / "analysis-worker.md").read_text()
        # Wrapper explicitly forbids these in its blinding clause, so the strings
        # will appear in the "MUST NOT" context -- that's fine. What we check is
        # that they don't appear as arguments being passed through.
        blinding_section = text.lower()
        assert "must not read any paper pdf" in blinding_section
        assert "questions_with_answers.xlsx" in blinding_section
        # The Skill invocation forwards only these four fields:
        assert '"mode": "answer_one"' in text
        assert '"question"' in text
        assert '"data_dir"' in text
        assert '"output_path"' in text
        # It must NOT forward paper_pdf inside the Skill(...) invocation block.
        # (It's OK for "paper_pdf" to appear in the blinding prose -- we only
        # care about what the wrapper actually passes downstream.)
        start = text.index("Skill(")
        depth = 0
        end = start
        for i in range(start + len("Skill(") - 1, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        invocation_block = text[start:end + 1]
        assert "paper_pdf" not in invocation_block

    def test_discrepancy_worker_wrapper_does_forward_paper_pdf(self):
        """Phase 3 is allowed to see the paper PDF; verify the wrapper forwards it."""
        text = (PLUGIN_ROOT / "agents" / "discrepancy-worker.md").read_text()
        assert '"mode": "compare"' in text
        assert "paper_pdf" in text

    def test_wrappers_stay_thin(self):
        """Collapsed wrappers should be well under the original 138/137 lines."""
        for name in ("analysis-worker.md", "discrepancy-worker.md"):
            lines = (PLUGIN_ROOT / "agents" / name).read_text().splitlines()
            assert len(lines) < 40, f"{name} grew to {len(lines)} lines; keep it thin"


class TestAnalyzeDataSkillSections:
    """Verify the analyze-data SKILL.md gained the new sections (milestone M5)."""

    def test_sections_present(self):
        text = (PLUGIN_ROOT / "skills" / "analyze-data" / "SKILL.md").read_text()
        assert "### 0e. Backend discovery" in text
        assert "## STEP 7: R / Bioconductor Recipes" in text
        assert "## STEP 8: scanpy Recipes" in text
        assert "## STEP 9: Single-Question Mode" in text
        assert "answer_one" in text
        assert "compare" in text

    def test_single_question_schema_matches_discrepancy_worker(self):
        text = (PLUGIN_ROOT / "skills" / "analyze-data" / "SKILL.md").read_text()
        # Must define the seven canonical root-cause codes so the compare-mode
        # output stays compatible with the legacy discrepancy-worker contract.
        for code in ("HUMAN_ANNOTATION_INCORRECT", "COHORT_FILTER_DIFFERENCE",
                     "VARIABLE_CHOICE", "VALUE_MAPPING", "DRUG_CLASSIFICATION",
                     "STATISTICAL_METHOD", "DEDUPLICATION_DIFFERENCE",
                     "MISSING_DATA_HANDLING", "UNKNOWN"):
            assert code in text

    def test_backend_discovery_probes_expected_packages(self):
        text = (PLUGIN_ROOT / "skills" / "analyze-data" / "SKILL.md").read_text()
        for pkg in ("minfi", "conumee", "limma", "edgeR", "fgsea", "ConsensusClusterPlus"):
            assert pkg in text
