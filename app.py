"""Streamlit 页面入口；通过 HTTP 提交审核，在会话中保存结果以支持页面重跑。

启动方式：streamlit run app.py。
"""

from uuid import uuid4

import streamlit as st

from review_system.api_client import APIClientError, APISettings, submit_review
from review_system.api_models import FailureResponse
from review_system.contracts import MAX_INPUT_CHARS, validate_review_request
from review_system.environment import load_project_env

load_project_env()

st.set_page_config(page_title="Multi-Agent Review")
st.title("Multi-Agent Review")
st.caption("Analyst → Critic → Judge")
review_mode = st.selectbox("Review mode", ["logic", "evidence"])
st.caption(
    "Logic: assumptions, consistency, and reasoning."
    if review_mode == "logic" else "Evidence: whether the supplied material supports its claims."
)
st.caption("Both modes use only your input; external facts are not verified.")
user_input = st.text_area(
    "Text, code, reasoning, or proposal to review", height=240,
    max_chars=MAX_INPUT_CHARS, help=f"Up to {MAX_INPUT_CHARS:,} characters.",
)


def display_response(response) -> None:
    """显示单个角色回答及所用模型；原始回答与下方结构化报告分别展示。"""
    st.subheader(response.agent)
    st.caption(f"Model: {response.model}")
    st.markdown(response.content)


def display_record(record) -> None:
    """展示阶段快照和已验证报告；格式非法的 Judge 原文单独标记，不作为最终报告。"""
    st.subheader("Stage status")
    st.caption(f"Review mode: {st.session_state.get('completed_review_mode', 'logic')}")
    st.table([
        {"Agent": stage.agent, "Model": stage.model, "Status": stage.status,
         "Error": stage.error_code or ""}
        for stage in record.stages
    ])
    for stage in record.stages:
        if stage.error_code == "invalid_output" and stage.raw_output is not None:
            st.warning(f"{stage.agent} output did not pass validation.")
            st.code(stage.raw_output, language="text")
    report = record.final_review
    if report is None:
        return
    st.subheader("Final report")
    st.metric("Verdict", report.verdict)
    st.text(report.summary)
    for index, finding in enumerate(report.findings, 1):
        st.subheader(f"Finding {index}: {finding.category} / {finding.severity}")
        st.text(finding.message)
        st.caption(f"Original input [{finding.start}:{finding.end}]")
        st.code(finding.quote, language="text")
        st.text(f"Suggestion: {finding.suggestion}")
    if report.limitations:
        st.subheader("Limitations")
        for limitation in report.limitations:
            st.text(limitation)


# Streamlit 交互会从头执行脚本；只有点击按钮才发起请求，历史结果从会话状态恢复。
if st.button("Review", type="primary"):
    # 新提交先清除上次展示结果，避免本次失败时仍显示旧报告。
    for key in ("review_result", "review_error", "review_record", "render_error"):
        st.session_state.pop(key, None)
    try:
        validate_review_request(user_input, review_mode)
        settings = APISettings.from_env()
        # 同一材料的提交结果未确认时复用 request_id；材料或模式变化才生成新标识。
        # 服务只在执行期间去重，复用标识并不保证完成后重提不会再次调用模型。
        pending = st.session_state.get("pending_submission")
        if pending is None or pending["original_input"] != user_input or pending["review_mode"] != review_mode:
            pending = {"request_id": str(uuid4()), "original_input": user_input, "review_mode": review_mode}
            st.session_state.pending_submission = pending
        with st.spinner("Reviewing… Results appear when the service finishes."):
            result = submit_review(**pending, settings=settings)
        # 先保存完整响应再展示；即使渲染失败，页面重跑仍能恢复已收到的结果。
        st.session_state.review_result = result.responses
        st.session_state.review_record = result
        st.session_state.completed_review_mode = review_mode
        if isinstance(result, FailureResponse):
            stage = f"{result.error.stage}: " if result.error.stage else ""
            st.session_state.review_error = f"{stage}{result.error.message} ({result.error.code})"
        # 执行中重复请求仍保留待确认标识；其他可信响应表示本次提交已有明确结果。
        if not isinstance(result, FailureResponse) or result.error.code != "duplicate_request":
            st.session_state.pop("pending_submission", None)
    except (APIClientError, ValueError) as exc:
        st.session_state.review_error = str(exc)

# 展示只读取会话快照，不在重跑时重复提交审核。
if record := st.session_state.get("review_record"):
    if record.execution_mode == "fake":
        st.warning("FAKE / Offline demonstration — these results do not assess your material.")
    else:
        st.caption("Live model response")
    if record.review_id:
        st.caption(f"Review ID: {record.review_id}")
    try:
        for response in st.session_state.get("review_result", ()):
            display_response(response)
        if record.stages:
            display_record(record)
    except Exception:
        st.error("Could not display the complete result. It is saved in this session; rerun to display it again.")

if error := st.session_state.get("review_error"):
    st.error(error)

if pending := st.session_state.get("pending_submission"):
    st.info(
        "The outcome is not confirmed. Submitting the same material again reuses its request ID. "
        "The service only rejects duplicates while they are running; resubmitting after completion can run the models again."
    )
    st.caption(f"Pending request ID: {pending['request_id']}")
