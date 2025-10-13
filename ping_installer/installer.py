#!/usr/bin/env python3

import os
import sys
import time
import platform
import traceback
from pathlib import Path
from threading import Event

import requests
from dotenv import load_dotenv
from PyQt5 import QtCore, QtGui, QtWidgets

load_dotenv()

IS_WINDOWS = platform.system() == "Windows"

DEFAULT_URL = os.getenv(
    "GITHUB_DOWNLOAD_URL",
    "https://github.com/shaekenit/pinger/raw/main/dist/Pinger.exe"
)

LOCAL_APP_DIR = Path(
    os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local") if IS_WINDOWS else Path.home()
) / "Pinger"


class Downloader(QtCore.QThread):
    progress_changed = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(bool, str)
    log = QtCore.pyqtSignal(str)

    def __init__(self, url: str, target_path: Path, stop_event: Event = None, parent=None):
        super().__init__(parent)
        self.url = url
        self.target_path = Path(target_path)
        self._stop_event = stop_event or Event()
        self._chunk_size = 8192

    def run(self):
        start_time = time.time()
        downloaded_bytes = 0
        self.log.emit(f"Starting download from: {self.url}")

        try:
            with requests.get(self.url, stream=True, timeout=20) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                temp_file = self.target_path.with_suffix(".download")
                temp_file.parent.mkdir(parents=True, exist_ok=True)

                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=self._chunk_size):
                        if self._stop_event.is_set():
                            self.log.emit("Download cancelled by user.")
                            temp_file.unlink(missing_ok=True)
                            self.finished.emit(False, "Cancelled")
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            self.progress_changed.emit(downloaded_bytes, total_size)

                try:
                    temp_file.replace(self.target_path)
                except PermissionError as pe:
                    self.log.emit(f"Permission error: {pe}")
                    self.finished.emit(False, f"PERMISSION_DENIED_OVERWRITE:{self.target_path}")
                    return
                except Exception as e:
                    self.log.emit(f"Error moving file: {e}")
                    self.finished.emit(False, str(e))
                    return

            elapsed = time.time() - start_time
            speed = downloaded_bytes / elapsed if elapsed > 0 else 0
            self.log.emit(f"Download complete: {downloaded_bytes} bytes in {elapsed:.1f}s ({speed/1024:.1f} KB/s).")
            self.finished.emit(True, "Downloaded")

        except Exception as e:
            tb = traceback.format_exc()
            self.log.emit(f"Download failed: {e}\n{tb}")
            self.finished.emit(False, str(e))

def create_windows_shortcut(target_path: str, shortcut_name="Pinger.lnk") -> bool:
    if not IS_WINDOWS:
        return False
    try:
        from win32com.client import Dispatch
        desktop = Path(os.environ['USERPROFILE']) / "Desktop"
        shortcut_file = desktop / shortcut_name
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(str(shortcut_file))
        shortcut.Targetpath = str(target_path)
        shortcut.WorkingDirectory = str(Path(target_path).parent)
        shortcut.IconLocation = str(target_path)
        shortcut.save()
        return True
    except Exception:
        return False


def create_url_fallback(target_path: str, name="Pinger.url") -> bool:
    try:
        desktop = Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        url_file = desktop / name
        content = (
            "[InternetShortcut]\n"
            f"URL=file:///{Path(target_path).resolve().as_posix()}\n"
            "IconIndex=0\n"
            f"IconFile={Path(target_path).resolve().as_posix()}\n"
        )
        url_file.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def relaunch_as_admin():
    if not IS_WINDOWS:
        return False, "Elevation only supported on Windows."
    try:
        import ctypes
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        res = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        if int(res) <= 32:
            return False, f"ShellExecuteW failed with code {res}"
        sys.exit(0)
    except Exception as e:
        return False, str(e)

GLOBAL_STYLE = """
QWidget { font-family: "Segoe UI", Arial, sans-serif; color: #e6edf0; background: transparent; }
QLabel { border: none; }
QLabel#bigtitle { font-size: 14pt; font-weight: 700; color: #e8eef0; }
QLineEdit, QTextEdit, QPlainTextEdit { background: #131416; border: 1px solid #232629; padding: 6px; color: #e6edf0; border-radius:6px; }
QPushButton { background: #1a1c1e; border: 1px solid #2b2f31; padding: 6px 10px; border-radius: 6px; color: #e6edf0; }
QPushButton:hover { background: #232629; }
QProgressBar { background: #0d0f10; border: 1px solid #222; border-radius: 8px; height: 18px; text-align: center; color: #e6edf0; }
QProgressBar::chunk { background: qlineargradient(x1:0, x2:1, stop:0 #2d9cdb, stop:1 #1b7fb0); border-radius: 8px; }
QToolButton { background: transparent; border: none; color: #9fb4bf; }
"""


class DotHandle(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dot_radius = 2.0
        self.spacing_x = 6.0
        self.spacing_y = 6.0
        self.dot_color = QtGui.QColor("#9fb4bf")
        self.cols, self.rows = 3, 2
        self._drag_offset = None
        self.setCursor(QtCore.Qt.SizeAllCursor)

    def minimumSizeHint(self):
        w = int(self.cols * (self.dot_radius * 2 + self.spacing_x))
        h = int(self.rows * (self.dot_radius * 2 + self.spacing_y))
        return QtCore.QSize(max(48, w + 8), max(20, h + 8))

    def paintEvent(self, ev):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.dot_color)

        w, h = float(self.width()), float(self.height())
        grid_w = (self.cols - 1) * self.spacing_x + self.cols * (self.dot_radius * 2)
        grid_h = (self.rows - 1) * self.spacing_y + self.rows * (self.dot_radius * 2)
        start_x = (w - grid_w) / 2.0 + self.dot_radius
        start_y = (h - grid_h) / 2.0 + self.dot_radius

        for col in range(self.cols):
            for row in range(self.rows):
                cx = start_x + col * (self.dot_radius * 2 + self.spacing_x)
                cy = start_y + row * (self.dot_radius * 2 + self.spacing_y)
                painter.drawEllipse(QtCore.QPointF(cx, cy), self.dot_radius, self.dot_radius)


    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self._drag_offset = ev.globalPos() - self.window().frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_offset and ev.buttons() & QtCore.Qt.LeftButton:
            new_pos = ev.globalPos() - self._drag_offset
            self.window().move(new_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag_offset = None
        ev.accept()


class CustomCheckBox(QtWidgets.QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._box_size = 18
        self.setStyleSheet("QCheckBox::indicator { width: 0; height: 0; }")
        self.setMinimumHeight(self._box_size + 6)

    def sizeHint(self):
        fm = QtGui.QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text())
        return QtCore.QSize(self._box_size + 8 + text_width, max(self._box_size + 6, fm.height() + 8))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        box_side = self._box_size
        box_x, box_y = 2, (rect.height() - box_side) // 2
        box_rect = QtCore.QRectF(box_x, box_y, box_side, box_side)

        painter.setPen(QtGui.QPen(QtGui.QColor("#2b2f31"), 1))
        painter.setBrush(QtGui.QColor("#131416"))
        painter.drawRoundedRect(box_rect, 4, 4)

        if self.isChecked():
            grad = QtGui.QLinearGradient(box_rect.topLeft(), box_rect.bottomRight())
            grad.setColorAt(0, QtGui.QColor("#2d9cdb"))
            grad.setColorAt(1, QtGui.QColor("#1b7fb0"))
            painter.setBrush(QtGui.QBrush(grad))
            painter.setPen(QtGui.QPen(QtGui.QColor("#1b7fb0")))
            painter.drawRoundedRect(box_rect.adjusted(1, 1, -1, -1), 3, 3)

            path = QtGui.QPainterPath()
            path.moveTo(box_x + box_side * 0.22, box_y + box_side * 0.53)
            path.lineTo(box_x + box_side * 0.44, box_y + box_side * 0.75)
            path.lineTo(box_x + box_side * 0.78, box_y + box_side * 0.28)
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2.25, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            painter.drawPath(path)

        painter.setPen(QtGui.QColor("#e6edf0"))
        fm = painter.fontMetrics()
        text_x = box_x + box_side + 8
        text_y = (rect.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(QtCore.QPoint(text_x, text_y), self.text())


class CloseButton(QtWidgets.QPushButton):
    def __init__(self, parent=None, diameter=28):
        super().__init__(parent)
        self._diameter = diameter
        self.setFixedSize(self._diameter, self._diameter)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: #1f2223;
                border: 1px solid #2e2e2e;
                border-radius: {self._diameter // 2}px;
                color: #f5dddd;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff6b65, stop:1 #e64b3b);
                color: white;
                border: 1px solid #d94b3b;
            }}
            QPushButton:pressed {{ background: #c74335; }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        r = self.rect().adjusted(8, 8, -8, -8)
        painter.drawLine(r.topLeft(), r.bottomRight())
        painter.drawLine(r.bottomLeft(), r.topRight())


class TitleBar(QtWidgets.QWidget):
    closeRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        layout.addStretch()
        self.handle = DotHandle(self)
        self.handle.setFixedSize(90, 34)
        layout.addWidget(self.handle)
        layout.addStretch()

        self.close_btn = CloseButton(self, diameter=28)
        layout.addWidget(self.close_btn)
        self.close_btn.clicked.connect(lambda: self.closeRequested.emit())

class InstallerWindow(QtWidgets.QWidget):
    def __init__(self):
        flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window
        super().__init__(None, flags)
        self.setWindowTitle("Pinger — Installer")
        self.resize(700, 480)
        self.setStyleSheet(GLOBAL_STYLE)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._radius = 14

        self.stop_event = Event()
        self.downloader = None
        self.current_target = None

        self._setup_ui()

        if not IS_WINDOWS:
            self.append_log("Note: non-Windows OS detected; desktop .lnk creation will fallback to .url.")

    def _setup_ui(self):
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(0)

        card = QtWidgets.QFrame()
        card.setStyleSheet("QFrame { background: #0f1113; border-radius: 12px; }")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        self.titlebar = TitleBar(self)
        self.titlebar.closeRequested.connect(self.request_close)
        card_layout.addWidget(self.titlebar)

        form = QtWidgets.QFormLayout()
        self.url_edit = QtWidgets.QLineEdit(DEFAULT_URL)
        self.path_edit = QtWidgets.QLineEdit(str(LOCAL_APP_DIR))
        self.browse_btn = QtWidgets.QToolButton(text="Browse")
        self.browse_btn.clicked.connect(self.choose_folder)

        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)

        form.addRow(QtWidgets.QLabel("Download URL"), self.url_edit)
        form.addRow(QtWidgets.QLabel("Install folder"), path_layout)
        card_layout.addLayout(form)

        options_layout = QtWidgets.QHBoxLayout()
        self.shortcut_cb = CustomCheckBox("Create desktop shortcut")
        self.shortcut_cb.setChecked(IS_WINDOWS)
        self.runafter_cb = CustomCheckBox("Run after install")
        self.runafter_cb.setChecked(True)
        options_layout.addWidget(self.shortcut_cb)
        options_layout.addWidget(self.runafter_cb)
        options_layout.addStretch()
        card_layout.addLayout(options_layout)

        self.progress = QtWidgets.QProgressBar()
        self.status_label = QtWidgets.QLabel("Ready.")
        card_layout.addWidget(self.progress)
        card_layout.addWidget(self.status_label)

        btn_layout = QtWidgets.QHBoxLayout()
        self.install_btn = QtWidgets.QPushButton("Install")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.install_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(2000)
        card_layout.addWidget(self.log_area, 1)

        outer_layout.addWidget(card)

        self.install_btn.clicked.connect(self.on_install_clicked)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)

    def append_log(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self.log_area.appendPlainText(f"[{ts}] {text}")
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def choose_folder(self):
        chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose install folder", str(LOCAL_APP_DIR))
        if chosen:
            self.path_edit.setText(chosen)

    def on_install_clicked(self):
        self.current_target = Path(self.path_edit.text()) / "Pinger.exe"
        url = self.url_edit.text().strip()
        if not url:
            self.append_log("Error: Download URL is empty.")
            return

        self.append_log(f"Preparing download to {self.current_target}")
        self.progress.setValue(0)
        self.status_label.setText("Downloading...")
        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.stop_event.clear()

        self.downloader = Downloader(url, self.current_target, stop_event=self.stop_event)
        self.downloader.progress_changed.connect(self.update_progress)
        self.downloader.finished.connect(self.download_finished)
        self.downloader.log.connect(self.append_log)
        self.downloader.start()

    def on_cancel_clicked(self):
        self.stop_event.set()
        self.cancel_btn.setEnabled(False)

    def update_progress(self, done, total):
        if total > 0:
            percent = int(done / total * 100)
            self.progress.setValue(percent)

    def download_finished(self, success: bool, msg: str):
        self.cancel_btn.setEnabled(False)
        self.install_btn.setEnabled(True)
        if success:
            self.status_label.setText("Download complete.")
            if self.shortcut_cb.isChecked():
                if IS_WINDOWS:
                    if create_windows_shortcut(self.current_target):
                        self.append_log("Desktop shortcut created.")
                    else:
                        self.append_log("Failed to create Windows shortcut.")
                else:
                    if create_url_fallback(self.current_target):
                        self.append_log("Desktop .url created (fallback).")
            if self.runafter_cb.isChecked():
                try:
                    os.startfile(self.current_target) if IS_WINDOWS else os.system(f'"{self.current_target}" &')
                    self.append_log("Launched Pinger.")
                except Exception as e:
                    self.append_log(f"Failed to launch: {e}")
        else:
            self.status_label.setText(f"Error: {msg}")

    def request_close(self):
        if self.downloader and self.downloader.isRunning():
            self.append_log("Download in progress; cancelling before exit.")
            self.stop_event.set()
            self.downloader.wait()
        self.close()

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLE)
    window = InstallerWindow()
    screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    window.move(screen.center() - window.rect().center())
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
