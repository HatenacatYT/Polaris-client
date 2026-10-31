"""Custom Sky page; file handling and Roblox writes stay in core/custom_sky.py."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
                               QVBoxLayout, QWidget)

from ..core.custom_sky import (FACES, SKYBOXFIX_TARGETS, SkyError, apply_custom_sky, backup_summary,
                               default_target_root, load_texture_files, load_texture_folder,
                               load_texture_zip, restore_custom_sky, validate_face_targets,
                               verify_applied_targets)
from ..core.i18n import N_, tr
from ..core.roblox import roblox_process_running
from .dialogs import choose
from .pages import Page, btn, lbl
from .theme import ERR, MUTED, OK, WARN

log = logging.getLogger("polaris.ui.custom_sky")


class TextureDropArea(QFrame):
    dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self.setMinimumHeight(72)
        self.setStyleSheet("QFrame#card { border-style: dashed; }")
        layout = QVBoxLayout(self)
        self.label = QLabel(tr("ここに .tex ファイル、フォルダ、または ZIP をドロップ"))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("muted")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class CustomSkyPage(Page):
    title = N_("Custom Sky")

    def __init__(self, win):
        super().__init__(win)
        self._files: dict[str, str] = {}
        self._source_mode = ""
        self._source_path = ""
        self._busy = False
        self._state_check_pending = False
        self._row_labels: dict[str, QLabel] = {}
        self._target_combos: dict[str, QComboBox] = {}

        self.root.addWidget(lbl(tr("Roblox Sky の6方向テクスチャを読み込み、バックアップ付きで管理します。"), "muted"))

        self.detection = lbl()
        self.detection.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.root.addWidget(self.detection)

        source_card = QFrame(); source_card.setObjectName("card")
        source_layout = QVBoxLayout(source_card)
        source_layout.addWidget(lbl(tr("テクスチャの読み込み"), "h2"))
        source_layout.addWidget(lbl(tr("各ファイル名に方向名（Bk/Dn/Ft/Lf/Rt/Up、Back/Down/Front/Left/Right/Up）を含めてください。"), "muted"))
        source_layout.addLayout(self._method_buttons())
        self.drop_area = TextureDropArea()
        self.drop_area.dropped.connect(self._drop_paths)
        source_layout.addWidget(self.drop_area)
        self.root.addWidget(source_card)

        faces_card = QFrame(); faces_card.setObjectName("card")
        faces_layout = QVBoxLayout(faces_card)
        faces_layout.addWidget(lbl(tr("6方向の検証状態"), "h2"))
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(8)
        for row, face in enumerate(FACES):
            direction = lbl(tr(face.title()))
            direction.setMinimumWidth(95)
            state = lbl(tr("未読み込み"), "muted")
            self._row_labels[face] = state
            grid.addWidget(direction, row, 0)
            grid.addWidget(state, row, 1)
        faces_layout.addLayout(grid)
        self.root.addWidget(faces_card)

        mapping_card = QFrame(); mapping_card.setObjectName("card")
        mapping_layout = QVBoxLayout(mapping_card)
        mapping_layout.addWidget(lbl(tr("Roblox キャッシュへの割り当て"), "h2"))
        self.mapping_note = lbl(tr("skyboxfix のバッチには方向とハッシュ名の対応表がありません。根拠のない自動割り当てはせず、確認済みの対応を選択してください。"), "muted")
        mapping_layout.addWidget(self.mapping_note)
        targets_grid = QGridLayout()
        for row, face in enumerate(FACES):
            targets_grid.addWidget(lbl(tr(face.title())), row, 0)
            combo = QComboBox()
            combo.addItem(tr("割り当てなし"), "")
            for asset_id, prefix in SKYBOXFIX_TARGETS:
                combo.addItem(f"{asset_id}  ({prefix}/…)", asset_id)
            combo.currentIndexChanged.connect(self._save_mapping)
            self._target_combos[face] = combo
            targets_grid.addWidget(combo, row, 1)
        mapping_layout.addLayout(targets_grid)
        self.root.addWidget(mapping_card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.root.addWidget(self.progress)
        self.current_state = lbl(tr("適用状態: 未適用"), "muted")
        self.root.addWidget(self.current_state)

        actions = QHBoxLayout()
        self.apply_btn = btn(tr("適用"), self.apply, "primary")
        self.restore_btn = btn(tr("元に戻す"), self.restore)
        self.reload_btn = btn(tr("ファイルを再読み込み"), self.reload)
        actions.addWidget(self.apply_btn)
        actions.addWidget(self.restore_btn)
        actions.addWidget(self.reload_btn)
        actions.addStretch()
        self.root.addLayout(actions)
        self.root.addStretch()
        self._restore_saved_state()
        self._update_controls()

    def _method_buttons(self):
        row = QHBoxLayout()
        row.addWidget(btn(tr("6枚の .tex ファイルを選択"), self.choose_files))
        row.addWidget(btn(tr("フォルダを選択"), self.choose_folder))
        row.addWidget(btn(tr("ZIP ファイルを選択"), self.choose_zip))
        return row

    def _restore_saved_state(self):
        settings = self.core.settings.data
        self._files = dict(settings.custom_sky_files)
        self._source_path = settings.custom_sky_source
        self._source_mode = settings.custom_sky_source_mode
        targets = settings.custom_sky_face_targets
        for face, combo in self._target_combos.items():
            index = combo.findData(targets.get(face, ""))
            combo.setCurrentIndex(max(0, index))
        for face in FACES:
            path = self._files.get(face, "")
            if path and Path(path).is_file():
                self._row_labels[face].setText(tr("保存済み: {0}", Path(path).name))
                self._row_labels[face].setStyleSheet(f"color:{OK}")
            else:
                self._row_labels[face].setText(tr("未読み込み"))
                self._row_labels[face].setStyleSheet(f"color:{MUTED}")
        if self._source_path:
            self.drop_area.label.setText(tr("最後の入力: {0}", self._source_path))

    def _persist_files(self, mode: str, source_path: str, result: dict):
        settings = self.core.settings.data
        self._source_mode, self._source_path = mode, source_path
        self._files = dict(result["files"])
        if mode == "files":
            settings.custom_sky_name = tr("6枚のテクスチャ")
        else:
            settings.custom_sky_name = Path(source_path).name or tr("Custom Sky")
        settings.custom_sky_source = source_path
        settings.custom_sky_source_mode = mode
        settings.custom_sky_files = dict(self._files)
        self.core.settings.save()
        for face in FACES:
            details = result["details"][face]
            self._row_labels[face].setText(tr("検証済み: {0} ({1} bytes)", details["name"], details["size"]))
            self._row_labels[face].setStyleSheet(f"color:{OK}")
        self.drop_area.label.setText(tr("読み込み済み: {0}", source_path))
        self._set_notice(tr("6方向のファイル名、拡張子、サイズ、重複を確認しました。"), OK)
        self._update_controls()

    def _start_load(self, mode: str, source: str | list[str]):
        if self._busy:
            return
        self._set_busy(True)
        stage = self.core.paths.root / "custom_sky_staging"

        def work():
            if mode == "files":
                return load_texture_files(list(source))
            if mode == "folder":
                return load_texture_folder(source)
            if mode == "zip":
                return load_texture_zip(source, stage)
            raise SkyError(tr("不明な入力方法です"))

        source_text = "; ".join(map(str, source)) if isinstance(source, list) else str(source)
        self.win.run(work, lambda result: self._load_done(mode, source_text, result),
                     lambda error: self._operation_error(error, tr("ファイルを読み込めません")),
                     label=tr("テクスチャを検証中"))

    def _load_done(self, mode: str, source: str, result: dict):
        self._set_busy(False)
        self._persist_files(mode, source, result)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self.win, tr("6枚の .tex ファイルを選択"), "", tr("Roblox テクスチャ (*.tex)"))
        if paths:
            self._start_load("files", paths)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self.win, tr("テクスチャフォルダを選択"))
        if path:
            self._start_load("folder", path)

    def choose_zip(self):
        path, _ = QFileDialog.getOpenFileName(self.win, tr("ZIP ファイルを選択"), "", tr("ZIP アーカイブ (*.zip)"))
        if path:
            self._start_load("zip", path)

    def _drop_paths(self, paths: list[str]):
        if len(paths) == 1 and Path(paths[0]).is_dir():
            self._start_load("folder", paths[0])
        elif len(paths) == 1 and Path(paths[0]).suffix.casefold() == ".zip":
            self._start_load("zip", paths[0])
        else:
            self._start_load("files", paths)

    def reload(self):
        if not self._source_mode or not self._source_path:
            self.choose_files()
            return
        if self._source_mode == "files":
            self._start_load("files", [self._files[face] for face in FACES if face in self._files])
        elif self._source_mode == "folder":
            self._start_load("folder", self._source_path)
        elif self._source_mode == "zip":
            self._start_load("zip", self._source_path)
        else:
            self._set_notice(tr("再読み込み元が見つかりません。ファイルを選び直してください。"), WARN)

    def _face_targets(self) -> dict[str, str]:
        return {face: combo.currentData() for face, combo in self._target_combos.items() if combo.currentData()}

    def _save_mapping(self, *_):
        if not hasattr(self, "_target_combos"):
            return
        mapping = self._face_targets()
        self.core.settings.data.custom_sky_face_targets = mapping
        try:
            self.core.settings.save()
        except Exception:
            log.exception("custom_sky_mapping_save_failed")
        self._update_controls()

    def _update_controls(self):
        mapping_ok = False
        try:
            validate_face_targets(self._face_targets())
            mapping_ok = True
        except SkyError:
            pass
        self.apply_btn.setEnabled(bool(self._files) and mapping_ok and not self._busy)
        backup_id = self.core.settings.data.custom_sky_backup_id
        self.restore_btn.setEnabled(bool(backup_id) and not self._busy)
        self.reload_btn.setEnabled(not self._busy)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.progress.setVisible(busy)
        self._update_controls()

    def _set_notice(self, text: str, color: str):
        self.current_state.setText(text)
        self.current_state.setStyleSheet(f"color:{color}")

    def _operation_error(self, error, title: str):
        self._set_busy(False)
        self._set_notice(tr("失敗: {0}", error), ERR)
        choose(self.win, title, str(error), [tr("閉じる")], "error")

    def apply(self):
        if self._busy or not self._files:
            return
        try:
            targets = validate_face_targets(self._face_targets())
        except SkyError as exc:
            self._set_notice(str(exc), WARN)
            return
        if self.core.settings.data.confirm_before_apply:
            accepted = choose(
                self.win, tr("カスタムスカイを適用"),
                tr("対象の6キャッシュファイルを事前にバックアップし、内容を置き換えます。Robloxを終了してから続行してください。"),
                [tr("適用する"), tr("キャンセル")], "warn")
            if accepted != 0:
                return
        self._set_busy(True)

        def work():
            if os.name != "nt":
                raise SkyError(tr("Roblox キャッシュへの適用は Windows 10/11 でのみ実行できます。"))
            if roblox_process_running():
                raise SkyError(tr("適用前にRobloxを終了してください。"))
            install = self.core.detector.detect()
            root = default_target_root()
            return apply_custom_sky(self._files, targets, root,
                                    self.core.backup_dir() / "custom-sky", install.version_dir)

        self.win.run(work, self._apply_done,
                     lambda error: self._operation_error(error, tr("カスタムスカイを適用できません")),
                     label=tr("カスタムスカイを適用中"))

    def _apply_done(self, result: dict):
        self._set_busy(False)
        settings = self.core.settings.data
        settings.custom_sky_applied = True
        settings.custom_sky_backup_id = result["backup_id"]
        settings.custom_sky_applied_at = datetime.now().isoformat(timespec="seconds")
        settings.custom_sky_applied_version_dir = result["version_dir"]
        settings.custom_sky_applied_targets = {row["asset_id"]: row["sha256"] for row in result["applied"]}
        try:
            self.core.settings.save()
        except Exception as exc:
            self._set_notice(tr("ファイルは適用されましたが、設定を保存できませんでした: {0}", exc), WARN)
            return
        self._set_notice(tr("適用完了: {0}。バックアップ {1}", result["version_dir"], result["backup_id"]), OK)
        self.win.refresh_all()

    def restore(self):
        if self._busy:
            return
        settings = self.core.settings.data
        backup_id = settings.custom_sky_backup_id
        if not backup_id:
            self._set_notice(tr("復元できるバックアップがありません。"), WARN)
            return
        if choose(self.win, tr("元に戻す"),
                  tr("直近のカスタムスカイ適用前に保存した6ファイルの状態へ戻します。"),
                  [tr("元に戻す"), tr("キャンセル")], "warn") != 0:
            return
        self._set_busy(True)

        def work():
            root = default_target_root()
            return restore_custom_sky(self.core.backup_dir() / "custom-sky", backup_id, root)

        self.win.run(work, self._restore_done,
                     lambda error: self._operation_error(error, tr("バックアップを復元できません")),
                     label=tr("カスタムスカイを復元中"))

    def _restore_done(self, result: dict):
        self._set_busy(False)
        settings = self.core.settings.data
        settings.custom_sky_restore_backup_id = result.get("rollback_backup_id", "")
        settings.custom_sky_applied = False
        settings.custom_sky_applied_targets = {}
        try:
            self.core.settings.save()
        except Exception:
            log.exception("custom_sky_restore_state_save_failed")
        self._set_notice(tr("元に戻しました: {0} 個の対象を復元しました。", len(result.get("paths", []))), OK)
        self.win.refresh_all()

    def _verify_saved_state(self):
        if self._state_check_pending or not self.core.settings.data.custom_sky_applied:
            return
        settings = self.core.settings.data
        detection = self.core.last_detection
        if detection.install and settings.custom_sky_applied_version_dir != str(detection.install.version_dir):
            self._set_notice(tr("古い適用状態: Robloxのバージョンが変わっています。再検出後に適用し直してください。"), WARN)
            return
        expected = settings.custom_sky_applied_targets
        if not expected:
            self._set_notice(tr("適用済み（保存時の内容は再検証されていません）。"), WARN)
            return
        self._state_check_pending = True

        def work():
            root = default_target_root()
            return verify_applied_targets(root, expected)

        self.win.run(work, self._verification_done, lambda error: self._verification_done({"ok": False, "error": str(error)}),
                     label=tr("適用状態を確認中"))

    def _verification_done(self, result: dict):
        self._state_check_pending = False
        if result.get("ok"):
            self._set_notice(tr("適用済み: {0}", self.core.settings.data.custom_sky_applied_at), OK)
        else:
            self._set_notice(tr("適用状態を確認できません。対象のファイルが変更または削除されています。"), WARN)

    def refresh(self):
        detection = self.core.last_detection
        if detection.install:
            self.detection.setText(tr("Robloxを検出: {0}", detection.install.version_name))
            self.detection.setStyleSheet(f"color:{OK}")
        elif detection.code == "NOT_FOUND":
            self.detection.setText(tr("Robloxが見つかりません。適用にはインストールが必要です。"))
            self.detection.setStyleSheet(f"color:{ERR}")
        else:
            self.detection.setText(tr("Robloxの検出状態: {0}", detection.message or tr("確認中")))
            self.detection.setStyleSheet(f"color:{WARN}")
        summary = backup_summary(self.core.backup_dir() / "custom-sky",
                                 self.core.settings.data.custom_sky_backup_id)
        self.restore_btn.setEnabled(bool(summary) and not self._busy)
        self._verify_saved_state()
        self._update_controls()
