"""Tests for unified diff parsing."""

from diffdesk.diff_parse import guess_language, parse_unified_diff, render_diff_html_lines


SAMPLE = """\
diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 def main():
+    print("hi")
     return 0
diff --git a/README.md b/README.md
new file mode 100644
index 000..333
--- /dev/null
+++ b/README.md
@@ -0,0 +1,2 @@
+# Hello
+world
"""


def test_parse_empty():
    result = parse_unified_diff("")
    assert result.files == []
    result2 = parse_unified_diff("   \n")
    assert result2.files == []


def test_parse_multi_file():
    result = parse_unified_diff(SAMPLE)
    assert len(result.files) == 2
    paths = {f.path for f in result.files}
    assert paths == {"src/app.py", "README.md"}
    app = next(f for f in result.files if f.path == "src/app.py")
    assert app.language == "python"
    assert app.additions >= 1
    readme = next(f for f in result.files if f.path == "README.md")
    assert readme.language == "markdown"
    assert readme.additions == 2


def test_parse_deleted_file():
    text = """\
diff --git a/old.txt b/old.txt
deleted file mode 100644
index aaa..000
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2
"""
    result = parse_unified_diff(text)
    assert len(result.files) == 1
    assert result.files[0].path == "old.txt"
    assert result.files[0].deletions == 2


def test_guess_language():
    assert guess_language("foo/bar.py") == "python"
    assert guess_language("x.TSX") == "typescript"
    assert guess_language("Makefile") == "makefile"
    assert guess_language("noext") == "text"


def test_render_diff_lines():
    lines = render_diff_html_lines("+added\n-removed\n context\n@@ hunk @@\n")
    types = [l["type"] for l in lines]
    assert "add" in types
    assert "del" in types
    assert "ctx" in types
    assert "hunk" in types
