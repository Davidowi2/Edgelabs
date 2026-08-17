"""EdgeLabs Monitor — desktop app shell for the trading dashboard.

Opens the live dashboard (http://127.0.0.1:8080) inside a native window using
the system's Edge WebView2 (via pywebview). Double-click the Desktop shortcut to
launch. Requires the bot + dashboard to be running (auto-started at logon, or run
launcher/bot_launcher.bat / Start_EdgeLabs.bat).

If the dashboard isn't up yet, the window shows a hint and you can refresh.
"""
from __future__ import annotations

import os
import sys

import webview

DASH_URL = "http://127.0.0.1:8080/"
TITLE = "EdgeLabs Monitor — MT5 DEMO Bot"


def main() -> None:
    webview.create_window(
        TITLE,
        url=DASH_URL,
        width=1180,
        height=820,
        min_size=(900, 600),
        text_select=True,
        confirm_close=False,
    )
    webview.start()


if __name__ == "__main__":
    main()
