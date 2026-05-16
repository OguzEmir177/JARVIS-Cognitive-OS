"""
[V9.1] J.A.R.V.I.S. File Tool Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE_READ, FILE_WRITE, FILE_SUMMARIZE düzeltme testleri.

Test Kategorileri:
    - Alias çözümleme (_resolve_alias)
    - Dizin listeleme (FILE_READ → is_dir)
    - Dosya okuma (mevcut davranış korunuyor)
    - Dosya yazma (alias desteği)
    - Parameters format doğrulaması
    - Hata senaryoları
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tools.file_tool import (
    FileReadTool,
    FileWriteTool,
    FileSummarizeTool,
    _resolve_alias,
    PATH_ALIASES,
)
from tools.base_tool import ToolResult


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ALIAS ÇÖZÜMLEMESİ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestResolveAlias:
    """_resolve_alias() fonksiyonu testleri."""

    def test_masaustu_alias(self):
        """'masaüstü' → ~/Desktop."""
        result = _resolve_alias("masaüstü")
        assert result == Path.home() / "Desktop"

    def test_desktop_alias(self):
        """'desktop' → ~/Desktop."""
        result = _resolve_alias("desktop")
        assert result == Path.home() / "Desktop"

    def test_belgeler_alias(self):
        """'belgeler' → ~/Documents."""
        result = _resolve_alias("belgeler")
        assert result == Path.home() / "Documents"

    def test_indirmeler_alias(self):
        """'indirmeler' → ~/Downloads."""
        result = _resolve_alias("indirmeler")
        assert result == Path.home() / "Downloads"

    def test_case_insensitive(self):
        """Büyük/küçük harf duyarsız olmalı."""
        result = _resolve_alias("MASAÜSTÜ")
        assert result == Path.home() / "Desktop"

    def test_no_alias_match(self):
        """Alias eşleşmezse orijinal yol döner."""
        result = _resolve_alias("C:\\some\\random\\path")
        assert result == Path("C:\\some\\random\\path")

    def test_partial_match(self):
        """Alias, yolun bir parçası olarak da eşleşmeli."""
        result = _resolve_alias("masaüstü/dosyalar")
        assert result == Path.home() / "Desktop"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FILE_READ TESTLERİ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFileReadTool:
    """FileReadTool execute() testleri."""

    @pytest.mark.asyncio
    async def test_empty_path(self):
        """Boş yol → success=False."""
        tool = FileReadTool()
        result = await tool.execute({"file_path": ""}, {})
        assert result.success is False
        assert "yolu belirtilmedi" in result.message

    @pytest.mark.asyncio
    async def test_nonexistent_path(self):
        """Var olmayan dosya → success=False."""
        tool = FileReadTool()
        result = await tool.execute(
            {"file_path": "C:\\nonexistent\\file.txt"}, {}
        )
        assert result.success is False
        assert "bulunamadı" in result.message

    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path):
        """Normal dosya okuma çalışmalı."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Merhaba Dünya", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(test_file)}, {})
        assert result.success is True
        assert result.data["content"] == "Merhaba Dünya"
        assert result.data["file_name"] == "test.txt"

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        """Dizin yolu verilince dosyaları listele."""
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.pdf").touch()
        (tmp_path / "c.docx").touch()

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(tmp_path)}, {})
        assert result.success is True
        assert "files" in result.data
        assert len(result.data["files"]) == 3
        assert "3 dosya bulundu" in result.speak

    @pytest.mark.asyncio
    async def test_list_directory_with_alias(self):
        """'masaüstü' alias'ı ile dizin listeleme."""
        tool = FileReadTool()
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            pytest.skip("Desktop klasörü yok")

        result = await tool.execute({"file_path": "masaüstü"}, {})
        assert result.success is True
        assert "files" in result.data

    @pytest.mark.asyncio
    async def test_large_directory_speak_truncation(self, tmp_path):
        """10'dan fazla dosya varsa speak mesajında '... ve N tane daha'."""
        for i in range(15):
            (tmp_path / f"file_{i}.txt").touch()

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(tmp_path)}, {})
        assert result.success is True
        assert "5 tane daha" in result.speak

    @pytest.mark.asyncio
    async def test_file_truncation(self, tmp_path):
        """Büyük dosya kırpılmalı."""
        test_file = tmp_path / "big.txt"
        test_file.write_text("X" * 10000, encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(test_file)}, {})
        assert result.success is True
        assert "[...dosya kırpıldı...]" in result.data["content"]

    @pytest.mark.asyncio
    async def test_parameters_format(self):
        """Parameters JSON Schema formatında olmalı."""
        tool = FileReadTool()
        params = tool.parameters
        assert "file_path" in params
        assert isinstance(params["file_path"], dict)
        assert params["file_path"]["type"] == "string"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FILE_WRITE TESTLERİ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFileWriteTool:
    """FileWriteTool execute() testleri."""

    @pytest.mark.asyncio
    async def test_missing_separator(self):
        """'|' yoksa → success=False."""
        tool = FileWriteTool()
        result = await tool.execute({"file_path_and_content": "nope"}, {})
        assert result.success is False
        assert "Format" in result.message

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        """Normal dosya yazma."""
        target = tmp_path / "out.txt"
        tool = FileWriteTool()
        result = await tool.execute(
            {"file_path_and_content": f"{target}|Merhaba"}, {}
        )
        assert result.success is True
        assert target.read_text(encoding="utf-8") == "Merhaba"
        assert "kaydedildi" in result.message

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path):
        """Üst dizinleri otomatik oluşturmalı."""
        target = tmp_path / "a" / "b" / "c.txt"
        tool = FileWriteTool()
        result = await tool.execute(
            {"file_path_and_content": f"{target}|İçerik"}, {}
        )
        assert result.success is True
        assert target.exists()

    @pytest.mark.asyncio
    async def test_write_dir_only_error(self, tmp_path):
        """Sadece dizin verilirse → hata."""
        tool = FileWriteTool()
        result = await tool.execute(
            {"file_path_and_content": f"{tmp_path}|İçerik"}, {}
        )
        assert result.success is False
        assert "dosya adı" in result.message.lower()

    @pytest.mark.asyncio
    async def test_write_parameters_format(self):
        """Parameters JSON Schema formatında olmalı."""
        tool = FileWriteTool()
        params = tool.parameters
        assert "file_path_and_content" in params
        assert isinstance(params["file_path_and_content"], dict)
        assert params["file_path_and_content"]["type"] == "string"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FILE_SUMMARIZE TESTLERİ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFileSummarizeTool:
    """FileSummarizeTool execute() testleri."""

    @pytest.mark.asyncio
    async def test_summarize_without_brain(self, tmp_path):
        """Brain yoksa → ilk 500 karakter + '...'."""
        test_file = tmp_path / "doc.txt"
        test_file.write_text("A" * 1000, encoding="utf-8")

        tool = FileSummarizeTool()
        result = await tool.execute({"file_path": str(test_file)}, {})
        assert result.success is True
        assert len(result.data["summary"]) == 503  # 500 + "..."

    @pytest.mark.asyncio
    async def test_summarize_directory_fails(self, tmp_path):
        """Dizin özetlenemez → success=False."""
        (tmp_path / "a.txt").touch()
        tool = FileSummarizeTool()
        result = await tool.execute({"file_path": str(tmp_path)}, {})
        assert result.success is False
        assert "dizin" in result.message.lower()

    @pytest.mark.asyncio
    async def test_summarize_parameters_format(self):
        """Parameters JSON Schema formatında olmalı."""
        tool = FileSummarizeTool()
        params = tool.parameters
        assert "file_path" in params
        assert isinstance(params["file_path"], dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXPORT SCHEMAS ENTEGRASYONU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExportSchemasIntegration:
    """file_tool parameters → export_schemas() uyumluluğu."""

    def test_export_schemas_no_crash(self):
        """Düzeltilen parameters formatı export_schemas()'ı kırmıyor."""
        from tools.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register(FileReadTool())
        registry.register(FileWriteTool())
        registry.register(FileSummarizeTool())

        # Eskiden v.get('type') → AttributeError (str has no get)
        schema_text = registry.export_schemas()
        assert "FILE_READ" in schema_text
        assert "FILE_WRITE" in schema_text
        assert "FILE_SUMMARIZE" in schema_text

    def test_schema_contains_type(self):
        """Export edilen schema'da parametre tipi görünmeli."""
        from tools.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register(FileReadTool())

        schema_text = registry.export_schemas()
        assert "string" in schema_text
