from __future__ import annotations

from bs4 import BeautifulSoup, Comment
from bs4.element import ProcessingInstruction, Declaration, Doctype


NOISY_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "img",
    "picture",
    "source",
    "video",
    "audio",
    "iframe",
    "object",
    "embed",
    "meta",
    "link",
}

ALLOWED_GLOBAL_ATTRS = {
    "id",
    "class",
    "name",
    "type",
    "value",
    "placeholder",
    "href",
    "role",
    "for",
    "title",
    "alt",
    "checked",
    "disabled",
    "required",
    "readonly",
    "multiple",
    "selected",
    "method",
    "action",
}

ALLOWED_DATA_ATTRS = {"data-testid", "data-test", "data-qa", "data-cy"}

POSTMORTEM_NOISY_TAGS = {
    "script",
    "noscript",
    "canvas",
    "iframe",
    "object",
    "embed",
}

POSTMORTEM_ALLOWED_GLOBAL_ATTRS = ALLOWED_GLOBAL_ATTRS | {
    "src",
    "srcset",
    "sizes",
    "rel",
    "content",
    "charset",
    "http-equiv",
}


def _parse_html(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def sanitize_html(html: str, mode: str = "agent") -> str:
    soup = _parse_html(html)

    if mode == "postmortem":
        noisy_tags = POSTMORTEM_NOISY_TAGS
        allowed_attrs = POSTMORTEM_ALLOWED_GLOBAL_ATTRS
    else:
        noisy_tags = NOISY_TAGS
        allowed_attrs = ALLOWED_GLOBAL_ATTRS

    for tag_name in noisy_tags:
        for t in soup.find_all(tag_name):
            t.decompose()

    for node in soup.find_all(string=True):
        if isinstance(node, (Comment, ProcessingInstruction, Declaration, Doctype)):
            node.extract()

    for el in soup.find_all(True):
        attrs = dict(el.attrs)
        kept = {}
        for key, value in attrs.items():
            k = key.lower()
            if k in allowed_attrs:
                kept[key] = value
            elif k.startswith("aria-"):
                kept[key] = value
            elif k in ALLOWED_DATA_ATTRS:
                kept[key] = value
        el.attrs = kept

    return str(soup)
