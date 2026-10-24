"""Streamlit 重跑示例：将计数放入 session_state，使按钮交互后状态仍能保留。"""

import streamlit as st

st.title("观察 rerun 与会话状态")
# 脚本每次重跑都会执行初始化语句；setdefault 仅在键不存在时设置初始值。
st.session_state.setdefault("count", 0)
if st.button("增加一次"):
    st.session_state["count"] += 1
st.write("当前次数：", st.session_state["count"])
