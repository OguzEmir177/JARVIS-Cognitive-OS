"""
[V8.0] J.A.R.V.I.S. Plan Parser Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4+1 katmanlı plan parser'ın robustness testleri.

Test Kategorileri:
    - Katman 1: PLAN keyword + numaralandırılmış satırlar
    - Katman 2: [PLAN]...[/PLAN] bloğu
    - Katman 3: Tek satırlı [PLAN: TAG(arg) -> TAG(arg)]
    - Katman 4: Fallback — sadece protokol etiketlerini topla
    - Edge cases: bozuk/yarım/garip LLM çıktıları
    - Filtreler: WhatsApp dedup, cleanup guard
"""

import pytest
from core.planner import parse_plan, PlanNode, ExecutionPlan, _apply_filters


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KATMAN 0: STRICT JSON TREE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer0:
    """Katman 0: JSON tabanlı tree yapısını test eder."""

    def test_json_tree_parsing(self):
        """JSON tabanlı ağaç düzgün parse edilmeli."""
        response = '''
```json
{
  "hedef": "YouTube'da video bul ve izle",
  "alt_gorevler": [
    {
      "hedef": "Videoyu ara",
      "adimlar": [
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
```
'''
        plan = parse_plan(response)
        assert plan is not None
        assert plan.original_request == "YouTube'da video bul ve izle"
        assert plan.total_steps == 2
        
        # İlk alt görev kendi içinde adım içeriyor
        assert plan.steps[0].goal == "Videoyu ara"
        assert len(plan.steps[0].sub_nodes) == 1
        assert plan.steps[0].sub_nodes[0].protocol_tag == "YT_SEARCH"
        assert plan.steps[0].sub_nodes[0].argument == "python tutorial"
        
        # İkinci alt görev adımlar yerine direkt kendi üstünde protocol tutuyor
        assert plan.steps[1].goal == "Videoyu aç"
        assert plan.steps[1].protocol_tag == "YT_PLAY"
        assert plan.steps[1].argument == "python tutorial"
        assert len(plan.steps[1].sub_nodes) == 0

    def test_json_parsing_missing_keys_fallback(self):
        """Hatalı JSON (eksik anahtarlar = fallback)."""
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
        # Katman 1/2'ye fallback yaptı
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KATMAN 1: PLAN kelimesi + numaralandırılmış satırlar
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer1:
    """Katman 1: PLAN kelimesi geçiyor + numaralandırılmış adımlar."""

    def test_standard_numbered_plan_with_protocol_prefix(self):
        """[PROTOCOL: X] prefix'li numaralandırılmış satırlar."""
        response = (
            "İşte PLAN:\n"
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
        """PLAN kelimesi var ama [PLAN] formatı yok."""
        response = (
            "Size bir plan hazırladım:\n"
            "1. GOOGLE_SEARCH hava durumu\n"
            "2. WHATSAPP_MESSAGE Ablam"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[0].argument == "hava durumu"

    def test_plan_with_extra_noise_text(self):
        """LLM'in plan etrafına eklediği gereksiz metin ignorlanmalı."""
        response = (
            "Tabii efendim, hemen hallediyorum!\n"
            "PLAN:\n"
            "1. [PROTOCOL: YT_PLAY] lofi beats\n"
            "2. [PROTOCOL: WEB_OPEN] google.com\n"
            "Başka bir şey ister misiniz?"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].argument == "lofi beats"
        assert plan.steps[1].argument == "google.com"

    def test_plan_steps_sorted_by_number(self):
        """Adımlar numara sırasına göre sıralanmalı (LLM karıştırsa bile)."""
        response = (
            "PLAN:\n"
            "3. APP_OPEN Discord\n"
            "1. GOOGLE_SEARCH test\n"
            "2. YT_SEARCH müzik"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.steps[0].step_number == 1
        assert plan.steps[1].step_number == 2
        assert plan.steps[2].step_number == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KATMAN 2: [PLAN]...[/PLAN] bloğu
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer2:
    """Katman 2: Standart [PLAN]...[/PLAN] bloğu."""

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
        """[PLAN] bloğu içinde boş satırlar olabilir — atlanmalı."""
        response = (
            "[PLAN]\n"
            "\n"
            "1. YT_SEARCH müzik\n"
            "\n"
            "2. APP_OPEN Spotify\n"
            "\n"
            "[/PLAN]"
        )
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2

    def test_plan_block_with_protocol_prefix(self):
        """[PLAN] bloğu içinde [PROTOCOL:] prefix'li satırlar da çalışmalı."""
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
#  KATMAN 3: Tek satırlı [PLAN: TAG(arg) -> TAG(arg)]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanParserLayer3:
    """Katman 3: Tek satırlık kompakt plan formatı."""

    def test_single_line_plan_with_arrow(self):
        """ASCII ok (->) ile."""
        response = "[PLAN: GOOGLE_SEARCH(Python) -> APP_OPEN(Discord)]"
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "GOOGLE_SEARCH"
        assert plan.steps[0].argument == "Python"
        assert plan.steps[1].protocol_tag == "APP_OPEN"
        assert plan.steps[1].argument == "Discord"

    def test_single_line_plan_with_unicode_arrow(self):
        """→ (Unicode ok) ile de çalışmalı."""
        response = "[PLAN: YT_PLAY(lofi) → WEB_OPEN(google.com)]"
        plan = parse_plan(response)

        assert plan is not None
        assert plan.total_steps == 2
        assert plan.steps[0].protocol_tag == "YT_PLAY"

    def test_single_line_no_args(self):
        """Argümansız tag'ler de çalışmalı."""
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
    """Katman 4: Yapı bulunamadı ama birden fazla protokol var."""

    def test_multiple_protocol_tags_without_plan(self):
        """Birden fazla [PROTOCOL:] varsa sıralı adımlar olarak topla."""
        response = (
            "Hemen yapıyorum efendim.\n"
            "[PROTOCOL: GOOGLE_SEARCH] Python\n"
            "Sonra da şunu yapacağım:\n"
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
    """Kenar durumlar ve hata dayanıklılığı."""

    def test_no_plan_returns_none(self):
        """Plan yoksa None dönmeli."""
        response = "Merhaba efendim, size nasıl yardımcı olabilirim?"
        plan = parse_plan(response)
        assert plan is None

    def test_single_protocol_not_treated_as_plan(self):
        """Tek protokol plan değildir — None dönmeli."""
        response = "[PROTOCOL: GOOGLE_SEARCH] Python"
        plan = parse_plan(response)
        assert plan is None

    def test_empty_string(self):
        """Boş string → None."""
        assert parse_plan("") is None

    def test_only_whitespace(self):
        """Sadece boşluk → None."""
        assert parse_plan("   \n\n  ") is None

    def test_plan_with_digit_only_tag_ignored(self):
        """Tag sadece rakamsa atlanmalı (LLM hallucination)."""
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
        """[PLAN] açıldı ama [/PLAN] ile kapanmadı — Katman 1'e fallback."""
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
        """Adım sonundaki nokta temizlenmeli."""
        response = (
            "PLAN:\n"
            "1. GOOGLE_SEARCH Python dersleri.\n"
            "2. APP_OPEN Discord."
        )
        plan = parse_plan(response)

        assert plan is not None
        # Argümanlardaki son noktanın temizlenmiş olması beklenir
        for step in plan.steps:
            assert not step.argument.endswith(".")

    def test_execution_plan_properties(self):
        """ExecutionPlan property'lerinin doğruluğu."""
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
        """advance() sonrası current_step doğru ilerlemeli."""
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
        """get_context_summary() tamamlanan adımları listeler."""
        plan = ExecutionPlan(
            original_request="test",
            steps=[
                PlanNode(step_number=1, protocol_tag="A", argument="x",
                         status="completed", result_message="Başarılı"),
                PlanNode(step_number=2, protocol_tag="B", argument="y",
                         status="pending"),
            ],
        )

        summary = plan.get_context_summary()
        assert "Adım 1" in summary
        assert "Başarılı" in summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FİLTRELER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanFilters:
    """WhatsApp dedup ve cleanup guard filtreleri."""

    def test_duplicate_whatsapp_recipient_removed(self):
        """Aynı alıcıya tekrar WHATSAPP_MESSAGE → duplikat silinmeli."""
        steps = [
            PlanNode(step_number=1, protocol_tag="WHATSAPP_MESSAGE", argument="Ablam|Selam"),
            PlanNode(step_number=2, protocol_tag="WHATSAPP_MESSAGE", argument="Ablam|Nasılsın"),
            PlanNode(step_number=3, protocol_tag="GOOGLE_SEARCH", argument="test"),
        ]
        result_plan = _apply_filters(steps, "")

        whatsapp_steps = [
            s for s in result_plan.steps
            if s.protocol_tag == "WHATSAPP_MESSAGE"
        ]
        assert len(whatsapp_steps) == 1

    def test_different_recipients_preserved(self):
        """Farklı alıcılar korunmalı."""
        steps = [
            PlanNode(step_number=1, protocol_tag="WHATSAPP_MESSAGE", argument="Ablam|Selam"),
            PlanNode(step_number=2, protocol_tag="WHATSAPP_MESSAGE", argument="Annem|Merhaba"),
        ]
        result_plan = _apply_filters(steps, "")
        assert len(result_plan.steps) == 2

    def test_unsolicited_cleanup_step_removed(self):
        """Kullanıcı istemediği halde APP_KILL eklenirse filtrele."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
            PlanNode(step_number=2, protocol_tag="APP_KILL", argument="Chrome"),
        ]
        result_plan = _apply_filters(steps, "Google'da test arat")
        assert result_plan.steps[-1].protocol_tag != "APP_KILL"

    def test_requested_cleanup_step_preserved(self):
        """Kullanıcı 'kapat' diyorsa cleanup korunmalı."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
            PlanNode(step_number=2, protocol_tag="APP_KILL", argument="Chrome"),
        ]
        result_plan = _apply_filters(steps, "test arat ve chrome'u kapat")
        assert len(result_plan.steps) == 2
        assert result_plan.steps[-1].protocol_tag == "APP_KILL"

    def test_single_step_no_filter(self):
        """Tek adımlı planda filtre çalışmamalı."""
        steps = [
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="test"),
        ]
        result_plan = _apply_filters(steps, "")
        assert len(result_plan.steps) == 1

    def test_empty_steps_no_crash(self):
        """Boş step listesi → çökmemeli."""
        result_plan = _apply_filters([], "")
        assert len(result_plan.steps) == 0
