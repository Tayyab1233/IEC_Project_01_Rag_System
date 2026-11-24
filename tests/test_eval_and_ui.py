"""Automated test suite for evaluation harness and frontend web UI serving.

Covers:
- Static file serving at /ui and redirect on root /.
- Evaluation harness offline run verifying metrics computation, report generation, and guardrail accuracy.
"""

import json
import os
import pytest
from httpx import AsyncClient

from evals.run_eval import run_evaluation


@pytest.mark.asyncio
async def test_ui_static_serving(async_client: AsyncClient):
    """Verify that frontend static files are served at /ui and root redirects cleanly."""
    # 1. Root redirect check
    root_res = await async_client.get("/", follow_redirects=False)
    assert root_res.status_code in (307, 302, 301)
    assert root_res.headers.get("location") == "/ui"

    # 2. UI index serving
    ui_res = await async_client.get("/ui", follow_redirects=True)
    assert ui_res.status_code == 200
    assert "Production RAG Service" in ui_res.text
    assert "Active Tenant:" in ui_res.text
    assert "Grounded Query & Chat" in ui_res.text

    # 3. CSS stylesheet serving
    css_res = await async_client.get("/ui/styles.css")
    assert css_res.status_code == 200
    assert "--bg-primary" in css_res.text

    # 4. JS script serving
    js_res = await async_client.get("/ui/app.js")
    assert js_res.status_code == 200
    assert "handleFileUpload" in js_res.text


@pytest.mark.asyncio
async def test_evaluation_harness_offline(temp_dir):
    """Verify that evals/run_eval.py executes in offline mode, computing valid metrics and reports."""
    eval_output_dir = os.path.join(temp_dir, "eval_results")
    dataset_path = "evals/golden_dataset.json"

    assert os.path.exists(dataset_path), "Golden dataset must exist"

    # Execute evaluation in offline mode
    summary = await run_evaluation(
        dataset_path=dataset_path,
        output_dir=eval_output_dir,
        offline=True,
        sleep_seconds=0.0,
        user_id="test_eval_tenant",
    )

    # Assert metric thresholds
    retrieval = summary["retrieval"]
    assert retrieval["recall_at_k"] >= 0.85
    assert retrieval["mrr"] >= 0.80

    guardrails = summary["guardrails"]
    assert guardrails["prompt_injection_block_rate"] == 1.0
    assert guardrails["out_of_scope_refusal_rate"] >= 0.80

    gen_quality = summary["generation_quality"]
    assert gen_quality["faithfulness"] >= 0.85
    assert gen_quality["context_recall"] >= 0.80

    # Verify output reports exist on disk
    json_report = os.path.join(eval_output_dir, "eval_report.json")
    md_report = os.path.join(eval_output_dir, "eval_report.md")

    assert os.path.exists(json_report)
    assert os.path.exists(md_report)

    with open(json_report, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["total_cases"] == 15
        assert len(data["details"]) == 15

    with open(md_report, "r", encoding="utf-8") as f:
        md_text = f.read()
        assert "# Production RAG Service - Comprehensive Evaluation Report" in md_text
        assert "Recall@k" in md_text
        assert "Injection Block Rate" in md_text
