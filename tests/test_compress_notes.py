import pandas as pd

from onc_wrangler.extraction.compressor import (
    COMPRESSION_SYSTEM_PROMPT,
    build_document_prompt,
    compress_notes_dataframe,
    main,
)
from onc_wrangler.llm.base import LLMClient, LLMResponse


class FakeLLMClient(LLMClient):
    def __init__(self):
        self.prompts = []

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.prompts.append(
            {
                "prompt": prompt,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return LLMResponse(
            text=f"Summary for document {len(self.prompts)}.",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )


def test_compression_prompt_captures_required_clinical_rules():
    prompt = COMPRESSION_SYSTEM_PROMPT
    assert "three sentences or less" in prompt
    assert "multiple independent primary cancers" in prompt
    assert "Biomarkers are NOT routine laboratory" in prompt
    assert "tumor markers belong" in prompt
    assert "Spell drug names out in full" in prompt
    assert "International Prognostic Index" in prompt
    assert "planned next steps" in prompt


def test_build_document_prompt_includes_metadata_and_text():
    prompt = build_document_prompt(
        "Clinical document body",
        {
            "document_id": "doc-1",
            "patient_id": "patient-1",
            "date": "2025-01-02",
            "note_type": "progress",
        },
    )
    assert "- document_id: doc-1" in prompt
    assert "- patient_id: patient-1" in prompt
    assert "Clinical document body" in prompt


def test_compress_notes_dataframe_processes_individual_rows():
    client = FakeLLMClient()
    df = pd.DataFrame(
        {
            "patient_id": ["p1", "p1"],
            "date": ["2025-01-01", "2025-02-01"],
            "note_type": ["pathology", "progress"],
            "text": ["Document one text.", "Document two text."],
        }
    )

    result = compress_notes_dataframe(
        df,
        client,
        max_workers=1,
        max_tokens=256,
    )

    assert len(result) == 2
    assert result["summary"].tolist() == [
        "Summary for document 1.",
        "Summary for document 2.",
    ]
    assert len(client.prompts) == 2
    assert "Document one text." in client.prompts[0]["prompt"]
    assert "Document two text." not in client.prompts[0]["prompt"]
    assert "Document two text." in client.prompts[1]["prompt"]
    assert client.prompts[0]["system"] == COMPRESSION_SYSTEM_PROMPT
    assert client.prompts[0]["max_tokens"] == 256


def test_compress_notes_cli_requires_notes_without_config():
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("main([]) should require --notes-path")
