"""Tests for workspace filesystem tools and path security."""

import pytest
from praxis_agent_runtime.tools.builtin.workspace_fs import (
    FsListDirTool,
    FsReadFileTool,
    FsWriteFileTool,
    _resolve_safe,
)


class TestResolveSafe:
    def test_valid_path(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        resolved = _resolve_safe(str(tmp_path), "src")
        assert resolved == str(sub)

    def test_path_traversal_blocked(self, tmp_path):
        with pytest.raises(PermissionError, match="outside workspace"):
            _resolve_safe(str(tmp_path), "../../etc/passwd")

    def test_absolute_path_outside_blocked(self, tmp_path):
        with pytest.raises(PermissionError, match="outside workspace"):
            _resolve_safe(str(tmp_path), "/etc/passwd")


class TestFsReadFileTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("world")
        tool = FsReadFileTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "hello.txt"})
        assert result.success is True
        assert result.output == "world"

    def test_read_missing_file(self, tmp_path):
        tool = FsReadFileTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "nope.txt"})
        assert result.success is False

    def test_read_path_traversal(self, tmp_path):
        tool = FsReadFileTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "../../etc/passwd"})
        assert result.success is False
        assert "outside workspace" in result.error


class TestFsWriteFileTool:
    def test_write_creates_file(self, tmp_path):
        tool = FsWriteFileTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "output.txt", "content": "hello"})
        assert result.success is True
        assert (tmp_path / "output.txt").read_text() == "hello"
        assert result.evidence["size"] == 5

    def test_write_creates_parent_dirs(self, tmp_path):
        tool = FsWriteFileTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "sub/deep/file.txt", "content": "nested"})
        assert result.success is True
        assert (tmp_path / "sub" / "deep" / "file.txt").exists()

    def test_requires_approval(self):
        tool = FsWriteFileTool(workspace_root="/tmp")
        assert tool.requires_approval is True


class TestFsListDirTool:
    def test_list_root(self, tmp_path):
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        tool = FsListDirTool(workspace_root=str(tmp_path))
        result = tool.run({"path": "."})
        assert result.success is True
        assert "a.txt" in result.output
        assert "b.txt" in result.output
