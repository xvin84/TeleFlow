"""
Qt ↔ Telegram HTML helpers.

Code formatting fix:
  fontFixedPitch() is unreliable across Qt serialization rounds.
  We use a custom QTextFormat property (UserProperty + 1) as the
  canonical "this fragment is <code>" marker, and also set fontFamily
  so it visually looks like monospace in the editor.
"""

from PyQt6.QtGui import QFont, QTextCharFormat, QTextDocument, QTextFormat

# Stable custom property key — must be consistent across save/load
_CODE_PROP = QTextFormat.Property.UserProperty + 1


def set_code_format(fmt: QTextCharFormat, is_code: bool) -> None:
    """Apply or remove code formatting on a QTextCharFormat."""
    fmt.setProperty(_CODE_PROP, is_code)
    if is_code:
        fmt.setFontFamilies(["monospace", "Courier New", "Courier"])
        fmt.setFontFixedPitch(True)
    else:
        fmt.setFontFamilies([])
        fmt.setFontFixedPitch(False)


def is_code_format(fmt: QTextCharFormat) -> bool:
    """Return True if the format carries the code property."""
    prop = fmt.property(_CODE_PROP)
    if prop is True:
        return True
    # Fallback: detect monospace font as a best-effort for old documents
    if fmt.fontFixedPitch():
        return True
    fam = fmt.fontFamilies()
    if isinstance(fam, list):
        return any("mono" in f.lower() or "courier" in f.lower() for f in fam)
    if isinstance(fam, str):
        return "mono" in fam.lower() or "courier" in fam.lower()
    return False


def to_telegram_html(doc: QTextDocument) -> str:
    """Convert QTextDocument to Telegram HTML (parse_mode='html').

    Telegram supports: <b> <i> <u> <s> <code>
    Telegram does NOT support <br> — use bare newlines.
    """
    result = ""
    block = doc.begin()
    first_block = True
    while block.isValid():
        if not first_block:
            result += "\n"
        first_block = False
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                text = (
                    frag.text()
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                fmt = frag.charFormat()
                tags: list[str] = []
                if fmt.fontWeight() >= QFont.Weight.Bold.value:
                    tags.append("b")
                if fmt.fontItalic():
                    tags.append("i")
                if fmt.fontUnderline():
                    tags.append("u")
                if fmt.fontStrikeOut():
                    tags.append("s")
                if is_code_format(fmt):
                    tags.append("code")
                for t in tags:
                    result += f"<{t}>"
                result += text
                for t in reversed(tags):
                    result += f"</{t}>"
            it += 1
        block = block.next()
    return result.strip()


def telegram_html_to_display_html(stored: str) -> str:
    """Prepare stored text for loading into QTextEdit.setHtml().

    Stored text is either:
    - Native Qt HTML (starts with <html or <!DOC) — returned as-is
    - Telegram HTML with bare \\n — convert to <br> for display
    """
    if not stored:
        return ""
    if stored.lstrip().startswith(("<!DOC", "<html", "<p ")):
        return stored
    if "\n" in stored and "<br" not in stored:
        stored = stored.replace("\n", "<br>")
    return stored
