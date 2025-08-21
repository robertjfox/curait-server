import os
from typing import Optional


def hyperlink(url: str, label: Optional[str] = None) -> str:
    """Return an OSC 8 hyperlink string for supported terminals.

    Many modern terminals (iTerm2, VSCode, GNOME Terminal, Kitty) support OSC 8
    hyperlinks. For unsupported terminals, the escape codes will be shown
    harmlessly, so include the raw URL alongside when logging for readability.
    """
    safe_url = url or ""
    text = (label or safe_url).strip() or safe_url

    ESC = "\x1b"
    start = f"{ESC}]8;;{safe_url}{ESC}\\"
    end = f"{ESC}]8;;{ESC}\\"
    return f"{start}{text}{end}" 