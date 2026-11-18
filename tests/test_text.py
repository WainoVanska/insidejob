import pytest

from insidejob.text import html_to_text


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Hello</p>", "Hello"),
        ("<p>One</p><p>Two</p>", "One\n\nTwo"),
        ("<ul><li>a</li><li>b</li></ul>", "a\n\nb"),
        ("Fish &amp; chips&nbsp;today", "Fish & chips today"),
        ("<p>Keep <strong>inline</strong> text</p>", "Keep inline text"),
        ("<style>p{}</style><p>Visible</p><script>x()</script>", "Visible"),
        ("<p>Kesätyö, harjoittelija</p>", "Kesätyö, harjoittelija"),
        ("", ""),
    ],
)
def test_html_to_text(html, expected):
    assert html_to_text(html) == expected
