"""[V8.0] J.A.R.V.I.S. Plan Parser Test Suite
━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━
Robustness tests of 4+1 layer plan parser.

Test Categories:
    - Layer 1: PLAN keyword + numbered rows
    - Layer 2: [PLAN]...[/PLAN] block
    - Layer 3: Single line [PLAN: TAG(arg) -> TAG(arg)]
    - Layer 4: Fallback — collect only protocol tags
    - Edge cases: broken/incomplete/strange LLM outputs
    - Filters: WhatsApp dedup, cleanup guard"""

import pytest
from core.planner import parse_plan, PlanNode, ExecutionPlan, _apply_filters


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KATMAN 0: STRICT JSON TREE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer0:
    """Layer 0: Tests the JSON-based tree structure."""

    def test_json_tree_parsing(self):
        """The JSON-based tree must be parsed properly."""
        response = '''```json
{
  "target": "Find and watch videos on YouTube",
  "sub_tasks": [
    {
      "target": "Search video",
      "steps": [
        {"protocol": "YT_SEARCH", "arg": "python tutorial"}
      ]
    },
    {
      "hedef": "Videoyu aç",
      "protocol": "YT_PLAY",
      "arg": "python tutorial"
    }
  ]
}
```'''
        plan = parse_plan(response)
        assert plan is not None
        assert plan.original_request == "Find and watch videos on YouTube"
        assert plan.total_steps == 2
        
        # The first subtask contains steps within itself
        assert plan.steps[0].goal == "Videoyu ara"
        assert len(plan.steps[0].sub_nodes) == 1
        assert plan.steps[0].sub_nodes[0].protocol_tag == "YT_SEARCH"
        assert plan.steps[0].sub_nodes[0].argument == "python tutorial"
        
        # The second subtask keeps a protocol directly above itself instead of steps
        assert plan.steps[1].goal == "Open video"
        assert plan.steps[1].protocol_tag == "YT_PLAY"
        assert plan.steps[1].argument == "python tutorial"
        assert len(plan.steps[1].sub_nodes) == 0

    def test_json_parsing_missing_keys_fallback(self):
        """Bad JSON (missing keys = fallback)."""
        response = '''
```json
{
  "yanlis_isim": "deger"
}
```
[PLAN]
1. GOOGLE_SEARCH test
[/PLAN]
'''
        plan = parse_plan(response)
        assert plan is not None
        assert plan.total_steps == 1
        # Fallback to Layer 1/2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 1: word PLAN + numbered lines
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer1:
    """Layer 1: Word PLAN appears + numbered steps."""

    def test_standard_numbered_plan_with_protocol_prefix(self):
        """Numbered lines prefixed with [PROTOCOL: X]."""
        response = (
            "Here is the PLAN:\n"
            "1. [PROTOCOL: GOOGLE_SEARCH] Python dersleri\n"
            "2. [PROTOCOL: YT_SEARCH] asyncio tutorial\n"
            "3. [PROTOCOL: APP_OPEN] Discord"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 3
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[0].argument == "Python dersleri"
        assert plan.steps[1].protocol_tag == "YT_SEARCH"
        assert plan.steps[1].argument == "asyncio tutorial"
        assert plan.steps[2].protocol_tag == "APP_OPEN"
        assert plan.steps[2].argument == "Discord"

    def test_plan_keyword_without_brackets(self):
        """There is the word PLAN but there is no format [PLAN]."""
        response = (
            "I prepared a plan for you:\n"
            "1. GOOGLE_SEARCH hava durumu\n"
            "2. WHATSAPP_MESSAGE Ablam"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[0].argument == "hava durumu"

    def test_plan_with_extra_noise_text(self):
        """The unnecessary text LLM added around the plan should be ignored."""
        response = (
            "Tabii efendim, hemen hallediyorum!\n"
            "PLAN:\n"
            "1. [PROTOCOL: YT_PLAY] lofi beats\n"
            "2. [PROTOCOL: WEB_OPEN] google.com\n"
            "Would you like anything else?"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].argument == "lofi beats"
        assert plan.steps[1].argument == "google.com"

    def test_plan_steps_sorted_by_number(self):
        """The steps should be listed in numerical order (even if the LLM confuses them)."""
        response = (
            "PLAN:\n"
            "3. APP_OPEN Discord\n"
            "1. GOOGLE_SEARCH test\n"
            "2. YT_SEARCH music"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.steps[0].step_number == 1
        assert plan.steps[1].step_number == 2
        assert plan.steps[2].step_number == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 2: [PLAN]...[/PLAN] block
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer2:
    """Layer 2: Standard [PLAN]...[/PLAN] block."""

    def test_multiline_plan_block(self):
        response = (
            "[PLAN]\n"
            "1. GOOGLE_SEARCH Python dersleri\n"
            "2. APP_OPEN Discord\n"
            "[/PLAN]"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[1].protocol_tag == "APP_OPEN"

    def test_plan_block_with_empty_lines(self):
        """There may be blank lines within the [PLAN] block — they should be skipped."""
        response = (
            "[PLAN]\n"
            "\n"
            "1. YT_SEARCH music\n"
            "\n"
            "2. APP_OPEN Spotify\n"
            "\n"
            "[/PLAN]"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2

    def test_plan_block_with_protocol_prefix(self):
        """Lines with [PROTOCOL:] prefix in the [PLAN] block should also work."""
        response = (
            "[PLAN]\n"
            "[PROTOCOL: GOOGLE_SEARCH] test query\n"
            "[PROTOCOL: APP_OPEN] Notepad\n"
            "[/PLAN]"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 3: Single line [PLAN: TAG(arg) -> TAG(arg)]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer3:
    """Layer 3: Compact one-line plan format."""

    def test_single_line_plan_with_arrow(self):
        """with ASCII arrow (->)."""
        response = "[PLAN: GOOGLE_SEARCH(Python) -> APP_OPEN(Discord)]"
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[0].argument == "Python"
        assert plan.steps[1].protocol_tag == "APP_OPEN"
        assert plan.steps[1].argument == "Discord"

    def test_single_line_plan_with_unicode_arrow(self):
        """Should also work with → (Unicode arrow)."""
        response = "[PLAN: YT_PLAY(lofi) → WEB_OPEN(google.com)]"
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "YT_PLAY"

    def test_single_line_no_args(self):
        """Tags without arguments should also work."""
        response = "[PLAN: VISION -> APP_OPEN(Discord)]"
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "VISION"
        assert plan.steps[0].argument == ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KATMAN 4: Fallback — birden fazla [PROTOCOL:] topla
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer4:
    """Layer 4: No structure found but more than one protocol exists."""

    def test_multiple_protocol_tags_without_plan(self):
        """If there is more than one [PROTOCOL:], add them as sequential steps."""
        response = (
            "I'm doing it right away, sir.\n"
            "[PROTOCOL: GOOGLE_SEARCH] Python\n"
            "Then I will do this:\n"
            "[PROTOCOL: APP_OPEN] Discord"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[1].protocol_tag == "APP_OPEN"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EDGE CASES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserEdgeCases:
    """Edge cases and fault tolerance."""

    def test_no_plan_returns_none(self):
        """If there is no plan, None should be returned."""
        response = "Hello sir, how can I help you?"
        plan = parse_plan(response)
        assert plan is None

    def test_single_protocol_not_treated_as_plan(self):
        """A single protocol is not a plan — it should return None ."""
        response = "[PROTOCOL: GOOGLE_SEARCH] Python"
        plan = parse_plan(response)
        assert plan is None

    def test_empty_string(self):
        """Empty string → None."""
        assert parse_plan("") is None

    def test_only_whitespace(self):
        """Just space → None."""
        assert parse_plan("   \n\n  ") is None

    def test_plan_with_digit_only_tag_ignored(self):
        """If the tag is just numbers, it should be omitted (LLM hallucination)."""
        response = (
            "PLAN:\n"
            "1. 2 something\n"
            "2. GOOGLE_SEARCH real query"
        )
        plan = parse_plan(response)
        if plan:
            for step in plan.steps:
                assert not step.protocol_tag.isdigit()

    def test_truncated_plan_block(self):
        """[PLAN] opened but not closed with [/PLAN] — fallback to Layer 1."""
        response = (
            "[PLAN]\n"
            "1. GOOGLE_SEARCH test query\n"
            "2. APP_OPEN Discord"
            # [/PLAN] eksik
        )
        plan = parse_plan(response)
        assert plan is not None
        assert plan.total_steps >= 1

    def test_plan_step_with_trailing_period(self):
        """The dot at the end of the step should be cleared."""
        response = (
            "PLAN:\n"
            "1. GOOGLE_SEARCH Python dersleri.\n"
            "2. APP_OPEN Discord."
        )
        plan = parse_plan(response)

        assert plan is not None
        # The last point in the arguments is expected to be cleared
        for step in plan.steps:
            assert not step.argument.endswith(".")

    def test_execution_plan_properties(self):
        """Correctness of ExecutionPlan properties."""
        plan = ExecutionPlan(
            original_request="test",
            steps=[
                PlanNode(step_number=1, protocol_tag="A", argument="x", status="completed"),
                PlanNode(step_number=2, protocol_tag="B", argument="y", status="pending"),
            ],
        )

        assert plan.total_steps == 2
        assert plan.completed_count == 1
        assert not plan.is_complete
        assert plan.current_step is not None
        assert plan.current_step.protocol_tag == "A"

    def test_execution_plan_advance(self):
        """After advance() current_step should proceed correctly."""
        plan = ExecutionPlan(
            original_request="test",
            steps=[
                PlanNode(step_number=1, protocol_tag="A", argument="x"),
                PlanNode(step_number=2, protocol_tag="B", argument="y"),
            ],
        )

        plan.advance()
        assert plan.current_step.protocol_tag == "B"

        plan.advance()
        assert plan.is_complete
        assert plan.status == "completed"

    def test_execution_plan_context_summary(self):
        """get_context_summary() lists completed steps."""
        plan = ExecutionPlan(
            original_request="test",
            steps=[
                PlanNode(step_number=1, protocol_tag="A", argument="x",
                         status="completed", result_message="Successful"),
                PlanNode(step_number=2, protocol_tag="B", argument="y",
                         status="pending"),
            ],
        )

        summary = plan.get_context_summary()
        assert "Step 1" in summary
        assert "Successful" in summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILTERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanFilters:
    """WhatsApp dedup and cleanup guard filters."""

    def test_duplicate_whatsapp_recipient_removed(self):
        """WHATSAPP_MESSAGE → duplicate should be deleted again to the same recipient."""
        steps = [
            PlanNode(step_number=1, protocol_tag="WHATSAPP_MESSAGE", argument="Ablam|Selam"),
            PlanNode(step_number=2, protocol_tag="WHATSAPP_MESSAGE", argument="My sister|How are you?"),
            PlanNode(step_number=3, protocol_tag="GOOGLE_SEARCH", argument="test"),
        ]
        result_plan = _apply_filters(steps, "")

        whatsapp_steps = [
            s for s in result_plan.steps
            if s.protocol_tag == "WHATSAPP_MESSAGE"
        ]
        assert len(whatsapp_steps) == 1

    def test_different_recipients_preserved(self):
        """Different buyers must be protected."""
        steps = [
            PlanNode(step_number=1, protocol_tag="WHATSAPP_MESSAGE", argument="Ablam|Selam"),
            PlanNode(step_number=2, protocol_tag="WHATSAPP_MESSAGE", argument="Annem|Merhaba"),
        ]
        result_plan = _apply_filters(steps, "")
        assert len(result_plan.steps) == 2

    def test_unsolicited_cleanup_step_removed(self):
        """Filter if APP_KILL is added even though the user does not want it."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
            PlanNode(step_number=2, protocol_tag="APP_KILL", argument="Chrome"),
        ]
        result_plan = _apply_filters(steps, "Search for test on Google")
        assert result_plan.steps[-1].protocol_tag != "APP_KILL"

    def test_requested_cleanup_step_preserved(self):
        """If the user says 'close' the cleanup should be preserved."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
            PlanNode(step_number=2, protocol_tag="APP_KILL", argument="Chrome"),
        ]
        result_plan = _apply_filters(steps, "search for test and close chrome")
        assert len(result_plan.steps) == 2
        assert result_plan.steps[-1].protocol_tag == "APP_KILL"

    def test_single_step_no_filter(self):
        """In the one-step plan, the filter should not work."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
        ]
        result_plan = _apply_filters(steps, "")
        assert len(result_plan.steps) == 1

    def test_empty_steps_no_crash(self):
        """Empty step list → should not crash."""
        result_plan = _apply_filters([], "")
        assert len(result_plan.steps) == 0
