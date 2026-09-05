"""
step_logger.py

Turns browser_use's per-step callback into the timeline shape you asked to
match (title / duration / one-line description, each step completing in
sequence) -- the same shape as the "Dispute Response" reference screenshot:
a vertical list of {title, elapsed, description}.

Each step is:
  1. printed to the terminal immediately (so you see the agent think live)
  2. POSTed to the firewall's POST /agent/step, which writes it to the same
     audit_log + broadcasts it over the same WebSocket broadcaster that
     /checkout and /payments/capture already use (both proven in
     firewall/test_broadcaster.py) -- so a client (the future Expo app, or
     anything else) gets the identical live feed with zero new plumbing.

This module holds NO reasoning and makes NO firewall-outcome decisions --
it only observes and reports what the LLM-driven agent already decided to
do. The actual checkout gate is entirely in firewall/main.py.
"""
import time

import requests

FIREWALL_BASE_DEFAULT = "http://localhost:8000"


def _short_title(action_list) -> str:
    """First action's name, humanised -- e.g. 'click_element_by_index' ->
    'Click element'. Falls back to 'Thinking' if the step has no action yet."""
    if not action_list:
        return "Thinking"
    # each action is a small pydantic model wrapping exactly one field named
    # after the tool, e.g. {"click_element_by_index": {...}}
    try:
        name = next(iter(action_list[0].model_dump(exclude_none=True).keys()))
    except Exception:
        return "Agent step"
    return name.replace("_", " ").strip().capitalize()


def _highlight_box(browser_state_summary, action_list) -> dict | None:
    """Best-effort bounding box (as percentages of the viewport, matching the
    mobile app's overlay coordinate space) for whatever element the first
    action targeted -- e.g. {"click_element_by_index": {"index": 42}}. Purely
    an enhancement for the live "reading the page" view; any failure here
    must never break the actual reasoning pipeline, hence the broad guard."""
    try:
        if not action_list:
            return None
        action_dict = action_list[0].model_dump(exclude_none=True)
        params = next(iter(action_dict.values()))
        if not isinstance(params, dict):
            return None
        index = params.get("index")
        if index is None:
            return None

        selector_map = browser_state_summary.dom_state.selector_map
        node = selector_map.get(index)
        if node is None or node.absolute_position is None:
            return None
        rect = node.absolute_position

        page_info = browser_state_summary.page_info
        vw, vh = page_info.viewport_width, page_info.viewport_height
        if not vw or not vh:
            return None

        x_pct = (rect.x - page_info.scroll_x) / vw * 100
        y_pct = (rect.y - page_info.scroll_y) / vh * 100
        w_pct = rect.width / vw * 100
        h_pct = rect.height / vh * 100
        if x_pct < -20 or y_pct < -20 or x_pct > 120 or y_pct > 120:
            return None  # element is off-screen (scrolled out of the current viewport)
        return {"x": round(x_pct, 1), "y": round(y_pct, 1), "width": round(w_pct, 1), "height": round(h_pct, 1)}
    except Exception:
        return None


class StepLogger:
    """One instance per agent run. Pass `.on_step` as browser_use's
    `register_new_step_callback`."""

    def __init__(self, run_id: str, firewall_base: str = FIREWALL_BASE_DEFAULT,
                 report_to_firewall: bool = True):
        self.run_id = run_id
        self.firewall_base = firewall_base
        self.report_to_firewall = report_to_firewall
        self.steps: list[dict] = []
        self._last_ts = time.monotonic()

    def on_step(self, browser_state_summary, agent_output, step_number: int) -> None:
        now = time.monotonic()
        elapsed = now - self._last_ts
        self._last_ts = now

        action_list = getattr(agent_output, "action", None)
        title = _short_title(action_list)
        eval_prev = (getattr(agent_output, "evaluation_previous_goal", "") or "").strip()
        next_goal = (getattr(agent_output, "next_goal", "") or "").strip()
        description = " ".join(x for x in (eval_prev, next_goal) if x) or "(no stated goal)"
        url = getattr(browser_state_summary, "url", "") or ""
        screenshot = getattr(browser_state_summary, "screenshot", None)

        step = {
            "run_id": self.run_id,
            "step_number": step_number,
            "title": f"Step {step_number}: {title}",
            "duration_s": round(elapsed, 1),
            "description": description[:400],
            "url": url,
            "screenshot_base64": screenshot,
            "highlight_box": _highlight_box(browser_state_summary, action_list),
        }
        self.steps.append(step)

        print(f"  [{step['duration_s']:>5.1f}s] {step['title']}\n         {step['description']}")

        if self.report_to_firewall:
            try:
                requests.post(f"{self.firewall_base}/agent/step", json=step, timeout=5)
            except requests.RequestException as e:
                print(f"  (step log not delivered to firewall: {e})")

    def total_duration(self) -> float:
        return sum(s["duration_s"] for s in self.steps)
