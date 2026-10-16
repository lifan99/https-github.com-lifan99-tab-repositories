import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from review_system.agents import JUDGE
from review_system.contracts import (
    MAX_INPUT_CHARS,
    ContractError,
    ReviewRequest,
    parse_final_review,
    validate_review_request,
)

ORIGINAL = "仅用内存保存记录，重启后历史仍在。"
VALID_TEXT = (Path(__file__).parent / "fixtures/d2/valid_report.json").read_text()


@pytest.fixture
def report():
    return json.loads(VALID_TEXT)


def test_valid_report_fields_and_immutable_collections():
    result = parse_final_review(VALID_TEXT, ORIGINAL)
    assert result.verdict == "needs_revision"
    assert result.findings[0].quote == ORIGINAL[9:16]
    assert result.findings[0].category == "logic"
    assert result.findings[0].severity == "high"
    assert result.limitations == ("仅评估输入文字，未运行服务或检查实现。",)
    with pytest.raises(FrozenInstanceError):
        result.summary = "changed"


@pytest.mark.parametrize("mode", ["logic", "evidence"])
def test_request_preserves_unicode_whitespace_and_mode(mode):
    original = " \n中文🐍\r\n重复 重复 "
    assert validate_review_request(original, mode) == ReviewRequest(original, mode)
    assert validate_review_request(original, mode).original_input == original


@pytest.mark.parametrize("value", [None, True, 7, [], {}, "", " \n\t", "x" * (MAX_INPUT_CHARS + 1)])
def test_invalid_request_input(value):
    with pytest.raises(ContractError, match="original_input"):
        validate_review_request(value)


@pytest.mark.parametrize("mode", ["other", "LOGIC", " logic", None, True, [], {}])
def test_invalid_modes(mode):
    with pytest.raises(ContractError, match="review_mode"):
        validate_review_request("Input", mode)


def test_input_limit_is_inclusive():
    original = "测" * MAX_INPUT_CHARS
    assert validate_review_request(original).original_input == original


@pytest.mark.parametrize("text", [
    "not json", '```json\n{}\n```', '{} trailing', '{}{}', '[]', 'null', '123',
    '{"summary":"a","summary":"b"}',
    '{"nested":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
    '{"x":' + "9" * 5000 + '}', '[' * 1100 + '0' + ']' * 1100,
])
def test_reject_invalid_or_non_strict_json(text):
    with pytest.raises(ContractError, match="report"):
        parse_final_review(text, ORIGINAL)


@pytest.mark.parametrize("field", ["summary", "verdict", "findings", "limitations"])
def test_missing_report_fields(report, field):
    del report[field]
    with pytest.raises(ContractError, match="report"):
        parse_final_review(json.dumps(report), ORIGINAL)


def test_unknown_field_does_not_echo_private_field_name(report):
    report["synthetic-private"] = "private"
    with pytest.raises(ContractError) as caught:
        parse_final_review(json.dumps(report), ORIGINAL)
    assert "synthetic-private" not in str(caught.value)


@pytest.mark.parametrize("field, value", [
    ("summary", " "), ("summary", 1), ("verdict", "banana"), ("verdict", []),
    ("findings", {}), ("findings", None), ("limitations", "none"),
    ("limitations", [""]), ("limitations", [None]),
])
def test_invalid_report_types_and_values(report, field, value):
    report[field] = value
    with pytest.raises(ContractError, match=f"report.{field}"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("field, value", [
    ("category", "other"), ("category", []), ("severity", "urgent"),
    ("message", " "), ("suggestion", None), ("start", True), ("end", False),
    ("start", "9"), ("end", 16.0), ("start", -1), ("end", 100),
    ("start", 16), ("end", 8), ("start", 8), ("quote", "invented"), ("quote", ""),
])
def test_invalid_finding_fields(report, field, value):
    report["findings"][0][field] = value
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("field", ["category", "severity", "message", "suggestion", "start", "end", "quote"])
def test_missing_finding_fields(report, field):
    del report["findings"][0][field]
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("finding", [None, "text", [], {"extra": 1}])
def test_finding_must_have_exact_object_shape(report, finding):
    report["findings"] = [finding]
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("verdict, findings, limitations, field", [
    ("needs_revision", [], [], "findings"),
    ("pass", None, [], "verdict"),
    ("insufficient_evidence", [], [], "limitations"),
])
def test_cross_field_rules(report, verdict, findings, limitations, field):
    report.update(verdict=verdict, limitations=limitations)
    if findings is not None:
        report["findings"] = findings
    with pytest.raises(ContractError, match=f"report.{field}"):
        parse_final_review(json.dumps(report), ORIGINAL)


def test_pass_allows_medium_and_insufficient_evidence_allows_no_findings(report):
    report["verdict"] = "pass"
    report["findings"][0]["severity"] = "medium"
    assert parse_final_review(json.dumps(report), ORIGINAL).verdict == "pass"
    report.update(verdict="insufficient_evidence", findings=[])
    assert parse_final_review(json.dumps(report), ORIGINAL).findings == ()


def test_quotes_preserve_original_codepoint_positions_and_repeated_text(report):
    original = " \n🐍重复\n重复 "
    finding = report["findings"][0]
    report["findings"] = [
        {**deepcopy(finding), "start": 3, "end": 5, "quote": "重复"},
        {**deepcopy(finding), "start": 6, "end": 8, "quote": "重复"},
    ]
    parsed = parse_final_review(json.dumps(report), original)
    assert [item.start for item in parsed.findings] == [3, 6]
    assert [item.quote for item in parsed.findings] == ["重复", "重复"]


def test_bad_quote_error_does_not_echo_input_or_model_text(report):
    report["findings"][0]["quote"] = "synthetic-private"
    with pytest.raises(ContractError) as caught:
        parse_final_review(json.dumps(report), ORIGINAL)
    assert "synthetic-private" not in str(caught.value)
    assert ORIGINAL not in str(caught.value)


def test_judge_prompt_contains_a_contract_valid_example():
    marker = f'Complete example for original_input "{ORIGINAL}": '
    example = JUDGE.system_prompt.split(marker, 1)[1]
    assert parse_final_review(example, ORIGINAL).verdict == "needs_revision"
