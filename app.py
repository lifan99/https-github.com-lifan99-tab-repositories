"""Run with: streamlit run app.py."""

import streamlit as st

from review_system.clients import OpenAICompatibleClient
from review_system.config import Settings
from review_system.environment import load_project_env
from review_system.workflow import MAX_INPUT_CHARS, AgentResponse, WorkflowError, run_review


load_project_env()

st.set_page_config(page_title="Multi-Agent Review")
st.title("Multi-Agent Review")
st.caption("Analyst → Critic → Judge")
user_input = st.text_area(
    "Text, code, reasoning, or proposal to review", height=240,
    max_chars=MAX_INPUT_CHARS, help=f"Up to {MAX_INPUT_CHARS:,} characters.",
)


def display_response(response: AgentResponse) -> None:
    st.subheader(response.agent)
    st.caption(f"Model: {response.model}")
    st.markdown(response.content)


if st.button("Review", type="primary"):
    st.session_state.pop("review_result", None)
    st.session_state.pop("review_error", None)
    try:
        settings = Settings.from_env()
        with st.spinner("Reviewing…"):
            result = run_review(
                user_input, OpenAICompatibleClient(settings),
                analyst_model=settings.analyst_model,
                critic_model=settings.critic_model,
                judge_model=settings.judge_model,
                on_response=display_response,
            )
        st.session_state.review_result = result.responses
    except WorkflowError as exc:
        st.session_state.review_result = exc.completed
        st.session_state.review_error = str(exc)
        st.error(str(exc))
    except ValueError as exc:
        st.session_state.review_error = str(exc)
        st.error(str(exc))
else:
    for response in st.session_state.get("review_result", ()):
        display_response(response)
    if error := st.session_state.get("review_error"):
        st.error(error)
