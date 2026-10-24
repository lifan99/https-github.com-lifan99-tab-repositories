"""Regression checks for document moves, anchors and offline reading formats."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.check_docs import check_documents, main


def test_links_resolve_from_document_directory_after_move(tmp_path):
    source = tmp_path / "learning" / "今天.md"
    source.parent.mkdir()
    target = tmp_path / "project" / "examples" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("pass\n")
    source.write_text("[示例](../project/examples/demo.py)\n")
    assert check_documents([source]) == (1, [])
    target.unlink()
    checked, missing = check_documents([source])
    assert checked == 1
    assert len(missing) == 1
    assert "demo.py" in missing[0]


@pytest.mark.parametrize("target", ["#hello-world", "#hello-world-1", "#显式", "目标%20文件.md#中文标题"])
def test_explicit_unicode_and_duplicate_heading_anchors(tmp_path, target):
    source = tmp_path / "index.md"
    source.write_text(f'[link]({target})\n# Hello World\n## Hello World\n<a id="显式"></a>\n')
    (tmp_path / "目标 文件.md").write_text("# 中文标题\n")
    assert check_documents([source]) == (1, [])


def test_broken_fragment_is_reported_even_when_file_exists(tmp_path):
    source = tmp_path / "index.md"
    source.write_text("# Heading\n[link](#wrong-heading)\n")
    checked, missing = check_documents([source])
    assert checked == 1
    assert len(missing) == 1
    assert "missing fragment" in missing[0]


def test_fenced_examples_and_external_links_are_not_local_links(tmp_path):
    source = tmp_path / "index.md"
    source.write_text(
        '```md\n[example](missing.md)\n```\n'
        '~~~html\n<a href="missing.html">example</a>\n~~~\n'
        '[web](https://example.invalid/page)\n[mail](mailto:a@example.invalid)\n'
    )
    assert check_documents([source]) == (0, [])


def test_html_resources_fragments_and_escaped_examples(tmp_path):
    source = tmp_path / "book.html"
    source.write_text(
        '<h1 id="contents">Contents</h1><a href="#contents">Go</a>'
        '<img src="cover.png"><code>&lt;a href="not-a-link"&gt;</code>'
    )
    (tmp_path / "cover.png").write_bytes(b"synthetic image")
    assert check_documents([source]) == (2, [])


@pytest.mark.parametrize("chapter", ["chapter.xhtml#part", "chapter.xhtml#missing", "absent.xhtml"])
def test_epub_links_and_package_resources(tmp_path, chapter):
    source = tmp_path / "book.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr("EPUB/nav.xhtml", f'<a href="{chapter}">Read</a>')
        archive.writestr("EPUB/chapter.xhtml", '<h1 id="part">Title</h1>')
        archive.writestr("EPUB/package.opf", '<item href="chapter.xhtml"/>')
    checked, missing = check_documents([source])
    assert checked == 2
    assert len(missing) == (0 if chapter.endswith("#part") else 1)


def test_missing_explicit_root_fails(tmp_path, capsys):
    assert main([str(tmp_path / "absent")]) == 1
    assert "Missing root" in capsys.readouterr().out


def test_default_project_scan_does_not_require_personal_folders(tmp_path, monkeypatch):
    import scripts.check_docs as checker

    (tmp_path / "README.md").write_text("# Project\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "examples").mkdir()
    (tmp_path / "study").mkdir()
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "missing-home"))
    assert checker.main([]) == 0
    assert checker.main(["--include-personal"]) == 1


def test_default_project_scan_includes_project_study_materials(tmp_path, monkeypatch):
    import scripts.check_docs as checker

    (tmp_path / "README.md").write_text("# Project\n")
    for name in ("docs", "examples", "study"):
        (tmp_path / name).mkdir()
    (tmp_path / "study" / "today.md").write_text("[task](missing-task.md)\n")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    assert checker.main([]) == 1


def test_extended_scan_uses_workspace_foundations_and_project_study(tmp_path, monkeypatch):
    import scripts.check_docs as checker

    home = tmp_path / "home"
    workspace = home / "ai-engineering"
    project = workspace / "multi-agent" / "mvp"
    for path in (project / "docs", project / "examples", project / "study", workspace / "learning", home / "career", home / "materials"):
        path.mkdir(parents=True)
    (project / "README.md").write_text("# Project\n")
    (project / "study" / "today.md").write_text("# Task\n")
    (workspace / "README.md").write_text("[course](learning/course.md)\n")
    course = workspace / "learning" / "course.md"
    course.write_text("[task](../multi-agent/mvp/study/today.md#task)\n")
    # The old home-level learning directory must no longer participate in navigation checks.
    (home / "learning").mkdir()
    (home / "learning" / "obsolete.md").write_text("[old](absent.md)\n")
    monkeypatch.setattr(checker, "ROOT", project)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert checker.main(["--include-personal"]) == 0
    course.write_text("[task](../multi-agent/mvp/study/absent.md)\n")
    assert checker.main(["--include-personal"]) == 1
