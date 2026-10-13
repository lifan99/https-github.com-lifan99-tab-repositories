import streamlit as st

st.title("观察 rerun 与会话状态")
st.session_state.setdefault("count", 0)
if st.button("增加一次"):
    st.session_state["count"] += 1
st.write("当前次数：", st.session_state["count"])
