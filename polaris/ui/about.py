"""About page."""
from __future__ import annotations

from .. import APP_NAME, __version__
from ..core.i18n import N_, tr
from .pages import Page, card, lbl


class AboutPage(Page):
    title = N_("About")

    def __init__(self, win):
        super().__init__(win)
        frame, content = card()
        content.addWidget(lbl(f"{APP_NAME}  v{__version__}", "h2"))
        content.addWidget(lbl(tr("Roblox Player の起動、FastFlags、バックアップ、カスタムスカイを管理する非公式ツールです。")))
        content.addWidget(lbl(tr("Roblox Corporation とは無関係です。ゲームの接続権限やアクセス制御を回避しません。"), "muted"))
        self.root.addWidget(frame)
        self.root.addStretch()
