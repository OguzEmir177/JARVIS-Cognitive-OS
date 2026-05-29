"""[V9.1] J.A.R.V.I.S. File Tool Test Suite
━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━
FILE_READ, FILE_WRITE, FILE_SUMMARIZE correction tests.

Test Categories:
    - Alias resolution (_resolve_alias)
    - Directory listing (FILE_READ → is_dir)
    - Reading files (current behavior is preserved)
    - File writing (alias support)
    - Parameters format verification
    - Error scenarios"""

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
# ALIAS ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestResolveAlias:
    """_resolve_alias() fonksiyonu testleri."""

    def test_masaustu_alias(self):
        """'desktop' → ~/Desktop."""
        result = _resolve_alias("desktop")
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
        """It should be case insensitive."""
        result = _resolve_alias("DESKTOP")
        assert result == Path.home() / "Desktop"

    def test_no_alias_match(self):
        """If the alias does not match, the original path is returned."""
        result = _resolve_alias("C:\\some\\random\\path")
        assert result == Path("C:\\some\\random\\path")

    def test_partial_match(self):
        """Alias ​​should also match part of the way."""
        result = _resolve_alias("desktop/files")
        assert result == Path.home() / "Desktop"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE_READ TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFileReadTool:
    """FileReadTool execute() testleri."""

    @pytest.mark.asyncio
    async def test_empty_path(self):
        """Empty path → success=False."""
        tool = FileReadTool()
        result = await tool.execute({"file_path": ""}, {})
        assert result.success is False
        assert "yolu belirtilmedi" in result.message

    @pytest.mark.asyncio
    async def test_nonexistent_path(self):
        """Non-existent file → success=False."""
        tool = FileReadTool()
        result = await tool.execute(
            {"file_path": "C:\\nonexistent\\file.txt"}, {}
        )
        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path):
        """Normal file reading should work."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(test_file)}, {})
        assert result.success is True
        assert result.data["content"] == "Hello world"
        assert result.data["file_name"] == "test.txt"

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        """List files given directory path."""
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
        """Directory listing with alias 'desktop'."""
        tool = FileReadTool()
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            pytest.skip("There is no desktop folder")

        result = await tool.execute({"file_path": "desktop"}, {})
        assert result.success is True
        assert "files" in result.data

    @pytest.mark.asyncio
    async def test_large_directory_speak_truncation(self, tmp_path):
        """If there are more than 10 files, the speak message will say '... and N more'."""
        for i in range(15):
            (tmp_path / f"file_{i}.txt").touch()

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(tmp_path)}, {})
        assert result.success is True
        assert "5 more" in result.speak

    @pytest.mark.asyncio
    async def test_file_truncation(self, tmp_path):
        """Large file should be cropped."""
        test_file = tmp_path / "big.txt"
        test_file.write_text("X" * 10000, encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute({"file_path": str(test_file)}, {})
        assert result.success is True
        assert "[...file clipped...]" in result.data["content"]

    @pytest.mark.asyncio
    async def test_parameters_format(self):
        """Parameters must be in JSON Schema format."""
        tool = FileReadTool()
        params = tool.parameters
        assert "file_path" in params
        assert isinstance(params["file_path"], dict)
        assert params["file_path"]["type"] == "string"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE_WRITE TESTS
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
        """It should create parent directories automatically."""
        target = tmp_path / "a" / "b" / "c.txt"
        tool = FileWriteTool()
        result = await tool.execute(
            {"file_path_and_content": f"{target}|Content"}, {}
        )
        assert result.success is True
        assert target.exists()

    @pytest.mark.asyncio
    async def test_write_dir_only_error(self, tmp_path):
        """→ error if only directory is given."""
        tool = FileWriteTool()
        result = await tool.execute(
            {"file_path_and_content": f"{tmp_path}|Content"}, {}
        )
        assert result.success is False
        assert "file name" in result.message.lower()

    @pytest.mark.asyncio
    async def test_write_parameters_format(self):
        """Parameters must be in JSON Schema format."""
        tool = FileWriteTool()
        params = tool.parameters
        assert "file_path_and_content" in params
        assert isinstance(params["file_path_and_content"], dict)
        assert params["file_path_and_content"]["type"] == "string"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE_SUMMARIZE TESTS
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
        """Index cannot be summarized → success=False."""
        (tmp_path / "a.txt").touch()
        tool = FileSummarizeTool()
        result = await tool.execute({"file_path": str(tmp_path)}, {})
        assert result.success is False
        assert "dizin" in result.message.lower()

    @pytest.mark.asyncio
    async def test_summarize_parameters_format(self):
        """Parameters must be in JSON Schema format."""
        tool = FileSummarizeTool()
        params = tool.parameters
        assert "file_path" in params
        assert isinstance(params["file_path"], dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXPORT SCHEMAS ENTEGRASYONU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExportSchemasIntegration:
    """file_tool parameters → export_schemas() compatibility."""

    def test_export_schemas_no_crash(self):
        """Fixed parameters format does not break export_schemas()."""
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
        """The parameter type must appear in the exported schema."""
        from tools.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register(FileReadTool())

        schema_text = registry.export_schemas()
        assert "string" in schema_text
