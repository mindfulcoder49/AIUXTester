from utils.html_cleaner import sanitize_html


def test_sanitize_html_removes_noisy_tags_and_comments():
    html = """
    <html>
      <head>
        <script>alert(1)</script>
        <style>body{}</style>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="/x.css" />
      </head>
      <body>
        <!-- comment -->
        <img src="/a.png" />
        <svg><circle /></svg>
        <div id="main">Hello</div>
      </body>
    </html>
    """
    out = sanitize_html(html)
    assert "<script" not in out
    assert "<style" not in out
    assert "<meta" not in out
    assert "<link" not in out
    assert "<img" not in out
    assert "<svg" not in out
    assert "comment" not in out
    assert 'id="main"' in out


def test_sanitize_html_attribute_allowlist():
    html = """
    <div
      id="x"
      class="a b"
      onclick="hack()"
      aria-label="Label"
      data-testid="ok"
      data-random="nope"
      custom-attr="drop"
      role="button"
    >Button</div>
    """
    out = sanitize_html(html)
    assert 'id="x"' in out
    assert 'class="a b"' in out
    assert 'aria-label="Label"' in out
    assert 'data-testid="ok"' in out
    assert 'role="button"' in out
    assert "onclick" not in out
    assert "data-random" not in out
    assert "custom-attr" not in out
