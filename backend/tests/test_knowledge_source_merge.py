"""Three-way Feishu/OIS comparison keeps divergent business edits visible."""
from plugins.knowledge.knowledge_backend.source_merge import merge_markdown


def test_nonoverlapping_feishu_and_local_edits_merge_without_conflict():
    result = merge_markdown("A\nB\nC\n", "A changed\nB\nC\n", "A\nB\nC local\n")
    assert result.conflicts == []
    assert result.merged == "A changed\nB\nC local\n"
    assert "A changed" in result.source_diff
    assert "C local" in result.local_diff


def test_same_line_edits_are_reported_not_silently_chosen():
    result = merge_markdown("A\nB\n", "A from Feishu\nB\n", "A from OIS\nB\n")
    assert result.conflicts
    assert result.conflicts[0]["base_range"] == [0, 1]
    assert result.merged is None


def test_unchanged_source_keeps_local_revision_without_new_content():
    result = merge_markdown("A\n", "A\n", "A locally edited\n")
    assert result.source_changed is False
    assert result.merged == "A locally edited\n"
