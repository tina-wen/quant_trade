from time import perf_counter

import streamlit as st


class PageProfiler:
    def __init__(self, page_name: str, enabled: bool):
        self.page_name = page_name
        self.enabled = enabled
        self._start = perf_counter()
        self._last = self._start
        self._events: list[tuple[str, float, float]] = []

    def mark(self, label: str):
        if not self.enabled:
            return
        now = perf_counter()
        since_last = (now - self._last) * 1000
        since_start = (now - self._start) * 1000
        self._events.append((label, since_last, since_start))
        self._last = now

    def render(self):
        if not self.enabled:
            return
        with st.sidebar.expander("性能诊断", expanded=False):
            st.caption(f"页面: {self.page_name}")
            if not self._events:
                st.caption("暂无采样点")
                return
            for label, delta_ms, total_ms in self._events:
                st.caption(f"{label}: +{delta_ms:.1f}ms (累计 {total_ms:.1f}ms)")


def init_page_profiler(page_name: str) -> PageProfiler:
    if "perf_debug" not in st.session_state:
        st.session_state.perf_debug = False
    st.sidebar.toggle("性能诊断模式", key="perf_debug")
    return PageProfiler(page_name=page_name, enabled=bool(st.session_state.perf_debug))
