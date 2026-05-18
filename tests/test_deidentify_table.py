import json

import pandas as pd

from onc_wrangler.deidentification.table import (
    DeidentificationConfig,
    classify_columns,
    deidentify_dataframe,
    main,
)
from onc_wrangler.llm.base import LLMClient, LLMResponse


class FakeStructuredLLMClient(LLMClient):
    def __init__(self):
        self.prompts = []

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise AssertionError("generate should not be called")

    def generate_structured(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(
            text=json.dumps(
                {
                    "deidentified_text": "Evelyn Carter remains clinically stable.",
                    "phi_removed": ["name"],
                    "review_required": False,
                }
            )
        )


def test_classify_columns_detects_phi_without_dropping_clinical_state():
    df = pd.DataFrame(
        {
            "patient_id": ["p1"],
            "MRN": ["A123"],
            "first_name": ["John"],
            "last_name": ["Smith"],
            "dob": ["1930-01-01"],
            "service_date": ["2020-01-01"],
            "age": [90],
            "evidence": ["John Smith had lung cancer."],
            "email": ["john@example.com"],
            "disease_state": ["metastatic"],
            "drug_name": ["pembrolizumab"],
        }
    )

    actions = {d.column: d.action for d in classify_columns(df)}

    assert actions["patient_id"] == "patient_id"
    assert actions["MRN"] == "mrn"
    assert actions["first_name"] == "name"
    assert actions["last_name"] == "name"
    assert actions["dob"] == "birth_date"
    assert actions["service_date"] == "date"
    assert actions["age"] == "age"
    assert actions["evidence"] == "text"
    assert actions["email"] == "drop"
    assert actions["disease_state"] == "keep"
    assert actions["drug_name"] == "keep"


def test_deidentify_dataframe_uses_stable_realistic_fake_names_and_manifest():
    df = pd.DataFrame(
        {
            "patient_id": ["p1", "p1", "p2"],
            "mrn": ["A12345", "A12345", "B67890"],
            "first_name": ["John", "John", "Jane"],
            "last_name": ["Smith", "Smith", "Doe"],
            "sex": ["M", "M", "F"],
            "evidence": [
                "John Smith MRN A12345 was seen.",
                "Smith returned for follow-up.",
                "Jane Doe MRN B67890 was seen.",
            ],
        }
    )

    result = deidentify_dataframe(df, DeidentificationConfig())
    out = result.dataframe

    assert out.loc[0, "patient_id"] == out.loc[1, "patient_id"]
    assert out.loc[0, "patient_id"] != out.loc[2, "patient_id"]
    assert out.loc[0, "patient_id"].startswith("patient_")
    assert out.loc[0, "mrn"].startswith("MRN")
    assert out.loc[0, "first_name"] != "John"
    assert out.loc[0, "last_name"] != "Smith"
    assert out.loc[0, "first_name"] not in {"Patient", "patient_000001"}
    assert "John" not in " ".join(out["evidence"].tolist())
    assert "Smith" not in " ".join(out["evidence"].tolist())
    assert "A12345" not in " ".join(out["evidence"].tolist())
    assert result.manifest["patients"]["p1"]["fake_name"] == (
        f"{out.loc[0, 'first_name']} {out.loc[0, 'last_name']}"
    )

    rerun = deidentify_dataframe(df, DeidentificationConfig(), manifest=result.manifest)
    pd.testing.assert_series_equal(out["first_name"], rerun.dataframe["first_name"])
    pd.testing.assert_series_equal(out["last_name"], rerun.dataframe["last_name"])
    pd.testing.assert_series_equal(out["patient_id"], rerun.dataframe["patient_id"])


def test_patient_date_shift_preserves_intervals_and_drops_dob():
    df = pd.DataFrame(
        {
            "patient_id": ["p1", "p1", "p2"],
            "dob": ["1930-01-01", "1930-01-01", "1970-01-01"],
            "service_date": ["2020-01-01", "2020-02-01", "2020-01-01"],
            "age": [90, 90, 50],
            "evidence": [
                "92-year-old seen on 2020-01-01.",
                "Age 93 on 2020-02-01.",
                "50-year-old seen on 2020-01-01.",
            ],
        }
    )

    result = deidentify_dataframe(df, DeidentificationConfig())
    out = result.dataframe

    assert "dob" not in out.columns
    assert out["age"].tolist() == ["90+", "90+", 50]
    shifted_dates = pd.to_datetime(out["service_date"])
    assert (shifted_dates.iloc[1] - shifted_dates.iloc[0]).days == 31

    p1_shift = result.manifest["patients"]["p1"]["date_shift_days"]
    expected = pd.Timestamp("2020-01-01") + pd.Timedelta(days=p1_shift)
    assert shifted_dates.iloc[0] == expected
    assert "92-year-old" not in out.loc[0, "evidence"]
    assert "Age 93" not in out.loc[1, "evidence"]
    assert "90+" in out.loc[0, "evidence"]
    assert "age 90+" in out.loc[1, "evidence"].lower()


def test_free_text_deterministic_redaction_removes_contacts_and_known_identifiers():
    df = pd.DataFrame(
        {
            "patient_id": ["p1"],
            "mrn": ["A12345"],
            "patient_name": ["John Smith"],
            "evidence": [
                "John Smith, MRN A12345, phone 555-123-4567, "
                "email john@example.com, address 123 Main St, seen 01/02/2020."
            ],
        }
    )

    result = deidentify_dataframe(df, DeidentificationConfig())
    text = result.dataframe.loc[0, "evidence"]

    assert "John Smith" not in text
    assert "A12345" not in text
    assert "555-123-4567" not in text
    assert "john@example.com" not in text
    assert "123 Main St" not in text
    assert "[PHONE]" in text
    assert "[EMAIL]" in text
    assert "[ADDRESS]" in text
    assert "2020-" in text


def test_llm_rewrites_only_text_cells_flagged_for_review():
    df = pd.DataFrame(
        {
            "patient_id": ["p1", "p2"],
            "evidence": ["Mr. Smith remains clinically stable.", "No PHI here."],
        }
    )
    client = FakeStructuredLLMClient()

    result = deidentify_dataframe(
        df,
        DeidentificationConfig(use_llm=True, text_columns=["evidence"]),
        llm_client=client,
    )

    assert len(client.prompts) == 1
    assert result.dataframe.loc[0, "evidence"] == "Evelyn Carter remains clinically stable."
    assert result.dataframe.loc[1, "evidence"] == "No PHI here."
    assert result.report["review_queue_rows"] == 0


def test_cli_rejects_cloud_llm_without_explicit_opt_in(tmp_path):
    input_path = tmp_path / "table.csv"
    pd.DataFrame({"patient_id": ["p1"], "evidence": ["Mr. Smith was seen."]}).to_csv(
        input_path,
        index=False,
    )

    try:
        main(
            [
                "--input-path",
                str(input_path),
                "--use-llm",
                "--provider",
                "anthropic",
                "--model",
                "claude-test",
            ]
        )
    except ValueError as exc:
        assert "--allow-cloud-llm" in str(exc)
    else:
        raise AssertionError("cloud LLM use should require explicit opt-in")
