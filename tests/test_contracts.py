"""v1 数据契约回归：覆盖严格 JSON、原文引用、字段规则及不可变报告。"""

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
    """每个用例重新解析报告样本，避免修改字典时相互污染。"""
    return json.loads(VALID_TEXT)


def test_valid_report_fields_and_immutable_collections():
    """有效报告可读取全部字段，冻结对象及元组保护已校验结果。"""
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
    """保留 Unicode 原文、首尾空白及调用方选择的模式。"""
    original = " \n中文🐍\r\n重复 重复 "
    assert validate_review_request(original, mode) == ReviewRequest(original, mode)
    assert validate_review_request(original, mode).original_input == original


@pytest.mark.parametrize("value", [None, True, 7, [], {}, "", " \n\t", "x" * (MAX_INPUT_CHARS + 1)])
def test_invalid_request_input(value):
    """空白、超长或类型错误的原文均不符合请求契约。"""
    with pytest.raises(ContractError, match="original_input"):
        validate_review_request(value)


@pytest.mark.parametrize("mode", ["other", "LOGIC", " logic", None, True, [], {}])
def test_invalid_modes(mode):
    """模式只接受精确的已知字符串，不做大小写或空白归一化。"""
    with pytest.raises(ContractError, match="review_mode"):
        validate_review_request("Input", mode)


def test_input_limit_is_inclusive():
    """恰好达到字符上限的输入仍然有效。"""
    original = "测" * MAX_INPUT_CHARS
    assert validate_review_request(original).original_input == original


@pytest.mark.parametrize("text", [
    "not json", '```json\n{}\n```', '{} trailing', '{}{}', '[]', 'null', '123',
    '{"summary":"a","summary":"b"}',
    '{"nested":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
    '{"x":' + "9" * 5000 + '}', '[' * 1100 + '0' + ']' * 1100,
])
def test_reject_invalid_or_non_strict_json(text):
    """拒绝重复键、非标准常量、代码围栏、尾随文本和过深嵌套。"""
    with pytest.raises(ContractError, match="report"):
        parse_final_review(text, ORIGINAL)


@pytest.mark.parametrize("field", ["summary", "verdict", "findings", "limitations"])
def test_missing_report_fields(report, field):
    """报告缺少任意必需字段都会失败。"""
    del report[field]
    with pytest.raises(ContractError, match="report"):
        parse_final_review(json.dumps(report), ORIGINAL)


def test_unknown_field_does_not_echo_private_field_name(report):
    """额外字段被拒绝，异常文本不回显未知字段名。"""
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
    """报告字段严格校验类型、非空白文本及枚举。"""
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
    """发现中的错误类型、非法枚举或引用坐标均被拒绝。"""
    report["findings"][0][field] = value
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("field", ["category", "severity", "message", "suggestion", "start", "end", "quote"])
def test_missing_finding_fields(report, field):
    """每条发现都必须具备完整字段。"""
    del report["findings"][0][field]
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("finding", [None, "text", [], {"extra": 1}])
def test_finding_must_have_exact_object_shape(report, finding):
    """发现必须是字段精确匹配的对象，不接受其他结构。"""
    report["findings"] = [finding]
    with pytest.raises(ContractError, match=r"report.findings\[0\]"):
        parse_final_review(json.dumps(report), ORIGINAL)


@pytest.mark.parametrize("verdict, findings, limitations, field", [
    ("needs_revision", [], [], "findings"),
    ("pass", None, [], "verdict"),
    ("insufficient_evidence", [], [], "limitations"),
])
def test_cross_field_rules(report, verdict, findings, limitations, field):
    """结论与问题数量、严重程度及限制说明必须满足跨字段规则。"""
    report.update(verdict=verdict, limitations=limitations)
    if findings is not None:
        report["findings"] = findings
    with pytest.raises(ContractError, match=f"report.{field}"):
        parse_final_review(json.dumps(report), ORIGINAL)


def test_pass_allows_medium_and_insufficient_evidence_allows_no_findings(report):
    """通过允许中等问题；证据不足允许没有具体问题但必须说明限制。"""
    report["verdict"] = "pass"
    report["findings"][0]["severity"] = "medium"
    assert parse_final_review(json.dumps(report), ORIGINAL).verdict == "pass"
    report.update(verdict="insufficient_evidence", findings=[])
    assert parse_final_review(json.dumps(report), ORIGINAL).findings == ()


def test_quotes_preserve_original_codepoint_positions_and_repeated_text(report):
    """引用按原文 Unicode 码点定位，重复文本也必须使用指定区间。"""
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
    """引用错误的异常不回显原文或模型文本。"""
    report["findings"][0]["quote"] = "synthetic-private"
    with pytest.raises(ContractError) as caught:
        parse_final_review(json.dumps(report), ORIGINAL)
    assert "synthetic-private" not in str(caught.value)
    assert ORIGINAL not in str(caught.value)


def test_judge_prompt_contains_a_contract_valid_example():
    """Judge 提示词中的完整报告示例也必须通过实际契约校验。"""
    marker = f'Complete example for original_input "{ORIGINAL}": '
    example = JUDGE.system_prompt.split(marker, 1)[1]
    assert parse_final_review(example, ORIGINAL).verdict == "needs_revision"
