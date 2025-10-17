#!/usr/bin/env python3

import sys
import os
import time
import uuid
import platform
import threading
import argparse
import requests
import json
import asyncio
import websockets
from requests.exceptions import RequestException
from PyQt5 import QtCore, QtGui, QtWidgets
from typing import Optional
import math
import wave
import struct
import tempfile
import atexit
import shutil
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
APP_NAME = "Pinger"
LOCAL_APP_DIR = (
    Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
)

APP_VERSION = "1.2.0"
GITHUB_REPO_OWNER = "shaekenit"
GITHUB_REPO_NAME = "pinger"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"


def check_for_updates():
    try:
        response = requests.get(
            GITHUB_RELEASES_URL,
            timeout=10,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
        )
        response.raise_for_status()

        release_data = response.json()
        latest_version = release_data.get("tag_name", "").lstrip("v")
        download_url = release_data.get("html_url", "")

        if not latest_version:
            return False, None, None, "No version tag found in release data"

        current_parts = [int(x) for x in APP_VERSION.split(".")]
        latest_parts = [int(x) for x in latest_version.split(".")]

        max_parts = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_parts - len(current_parts)))
        latest_parts.extend([0] * (max_parts - len(latest_parts)))

        for current, latest in zip(current_parts, latest_parts):
            if latest > current:
                return True, latest_version, download_url, None
            elif latest < current:
                return False, latest_version, download_url, None

        return False, latest_version, download_url, None

    except requests.exceptions.RequestException as e:
        return False, None, None, f"Network error: {e}"
    except Exception as e:
        return False, None, None, f"Error checking for updates: {e}"


def show_update_message(parent, latest_version, download_url):
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Update Available")
    dialog.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    dialog.setFixedSize(400, 280)

    dialog.setWindowFlags(
        QtCore.Qt.Dialog
        | QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.WindowStaysOnTopHint
    )

    main_widget = QtWidgets.QWidget(dialog)
    main_widget.setGeometry(0, 0, 400, 280)
    main_widget.setStyleSheet(f"""
        background-color: {COLORS["--background"]};
        border-radius: 12px;
    """)

    layout = QtWidgets.QVBoxLayout(main_widget)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    title_label = QtWidgets.QLabel("Update Available")
    title_label.setStyleSheet(f"""
        font-family: {FONT_FAMILY};
        font-size: 18px;
        font-weight: 600;
        color: {COLORS["--text"]};
    """)
    title_label.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(title_label)

    message_label = QtWidgets.QLabel(
        f"A new version of {APP_NAME} is available!\n\n"
        f"Current version: {APP_VERSION}\n"
        f"Latest version: {latest_version}"
    )
    message_label.setStyleSheet(f"""
        font-family: {FONT_FAMILY};
        font-size: 13px;
        color: {COLORS["--text"]};
        line-height: 1.4;
    """)
    message_label.setAlignment(QtCore.Qt.AlignCenter)
    message_label.setWordWrap(True)
    layout.addWidget(message_label)

    question_label = QtWidgets.QLabel("Would you like to download the update?")
    question_label.setStyleSheet(f"""
        font-family: {FONT_FAMILY};
        font-size: 12px;
        color: {COLORS["--muted"]};
        font-style: italic;
    """)
    question_label.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(question_label)

    layout.addStretch()

    button_layout = QtWidgets.QHBoxLayout()
    button_layout.setSpacing(16)
    button_layout.addStretch()

    no_button = QtWidgets.QPushButton("No")
    no_button.setFixedHeight(36)
    no_button.setStyleSheet(f"""
        QPushButton {{
            background-color: {COLORS["--secondary"]};
            color: {COLORS["--text"]};
            border: 1px solid {COLORS["--primary"]};
            border-radius: 8px;
            font-family: {FONT_FAMILY};
            font-size: 12px;
            font-weight: 600;
            min-width: 100px;
        }}
        QPushButton:hover {{
            background-color: {COLORS["--accent"]};
            border: 1px solid {COLORS["--highlight"]};
        }}
        QPushButton:pressed {{
            background-color: {COLORS["--primary"]};
        }}
    """)
    no_button.clicked.connect(dialog.reject)
    button_layout.addWidget(no_button)

    yes_button = QtWidgets.QPushButton("Yes")
    yes_button.setFixedHeight(36)
    yes_button.setStyleSheet(f"""
        QPushButton {{
            background-color: #2e7d32;
            color: {COLORS["--background"]};
            border: 1px solid #1b5e20;
            border-radius: 8px;
            font-family: {FONT_FAMILY};
            font-size: 12px;
            font-weight: 600;
            min-width: 100px;
        }}
        QPushButton:hover {{
            background-color: #45a049;
            border: 1px solid #388e3c;
        }}
        QPushButton:pressed {{
            background-color: #1b5e20;
            border: 1px solid #0f3d12;
        }}
    """)
    yes_button.clicked.connect(dialog.accept)
    button_layout.addWidget(yes_button)

    button_layout.addStretch()
    layout.addLayout(button_layout)

    if parent:
        dialog.move(parent.frameGeometry().center() - dialog.rect().center())

    result = dialog.exec_()
    if result == QtWidgets.QDialog.Accepted:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(download_url))


def check_updates_in_background(parent):
    def check():
        is_update, latest_version, download_url, error = check_for_updates()
        if error:
            print(f"Update check failed: {error}")
            return

        if is_update:
            QtCore.QMetaObject.invokeMethod(
                parent,
                "show_update_dialog",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, latest_version),
                QtCore.Q_ARG(str, download_url),
            )
        else:
            print(f"Running latest version: {APP_VERSION}")

    thread = threading.Thread(target=check, daemon=True)
    thread.start()


def create_windows_shortcut(target_path, shortcut_path):
    try:
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = str(target_path)
        shortcut.WorkingDirectory = str(Path(target_path).parent)
        shortcut.IconLocation = str(target_path)
        shortcut.save()
        return True
    except ImportError:
        print("win32com not available, creating .url shortcut instead")
        try:
            content = (
                "[InternetShortcut]\n"
                f"URL=file:///{Path(target_path).resolve().as_posix()}\n"
                "IconIndex=0\n"
                f"IconFile={Path(target_path).resolve().as_posix()}\n"
            )
            shortcut_path = shortcut_path.with_suffix(".url")
            shortcut_path.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            print(f"Failed to create .url shortcut: {e}")
            return False
    except Exception as e:
        print(f"Failed to create Windows shortcut: {e}")
        return False


def self_install():
    try:
        if getattr(sys, "frozen", False):
            current_exe = Path(sys.executable)
        else:
            current_exe = Path(sys.argv[0])
            if current_exe.suffix != ".exe":
                print("Running as Python script, skipping self-installation")
                return True

        if not current_exe.is_absolute():
            current_exe = Path.cwd() / current_exe
        current_exe = current_exe.resolve()

        target_exe = LOCAL_APP_DIR / f"{APP_NAME}.exe"

        if current_exe == target_exe:
            print("Already running from installed location, skipping self-installation")
            return True

        LOCAL_APP_DIR.mkdir(parents=True, exist_ok=True)

        print(f"Installing {APP_NAME} to: {target_exe}")
        shutil.copy2(current_exe, target_exe)
        print("Application copied to AppData")

        if IS_WINDOWS:
            try:
                desktop = Path.home() / "Desktop"
                shortcut_file = desktop / f"{APP_NAME}.lnk"
                if create_windows_shortcut(target_exe, shortcut_file):
                    print(f"Desktop shortcut created: {shortcut_file}")
                else:
                    print("Failed to create desktop shortcut")
            except Exception as e:
                print(f"Failed to create desktop shortcut: {e}")

        if IS_WINDOWS:
            try:
                start_menu = (
                    Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
                    / "Microsoft"
                    / "Windows"
                    / "Start Menu"
                    / "Programs"
                )
                start_menu.mkdir(parents=True, exist_ok=True)
                start_menu_shortcut = start_menu / f"{APP_NAME}.lnk"
                if create_windows_shortcut(target_exe, start_menu_shortcut):
                    print(f"Start Menu shortcut created: {start_menu_shortcut}")
                else:
                    print("Failed to create Start Menu shortcut")
            except Exception as e:
                print(f"Failed to create Start Menu shortcut: {e}")

        print("Self-installation completed successfully")
        return True

    except Exception as e:
        print(f"Self-installation failed: {e}")
        return False


try:
    from PyQt5.QtMultimedia import QSoundEffect
except Exception:
    QSoundEffect = None

if getattr(sys, "frozen", False):
    import warnings

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

DEFAULT_SERVER = "http://localhost:8000/"
DEFAULT_USERNAME = None
DEFAULT_INSTANCE = 1
USERNAME_FROM_DEVICE = True
DEV_MULTIPLE_INSTANCES = False

COLORS = {
    "--text": "#e8eeed",
    "--background": "#1a1a1a",
    "--dim-background": "#0C0C0C",
    "--primary": "#404040",
    "--secondary": "#2d2d2d",
    "--accent": "#555555",
    "--success": "#4caf50",
    "--error": "#f44336",
    "--muted": "#666666",
    "--highlight": "#7e7e7e",
}

DEFAULT_TIMEOUT = 5.0
WINDOW_RADIUS = 14
WINDOW_SIZE = 220
PING_POPUP_DURATION = 5000

ORGANIZATION_NAME = "Pinger"
ORGANIZATION_DOMAIN = "pinger.local"
FONT_FAMILY = "Segoe UI, Inter, Roboto, -apple-system, BlinkMacSystemFont, sans-serif"


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def generate_uid():
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid1())


def derive_username(cli_username, instance):
    if USERNAME_FROM_DEVICE:
        devname = platform.node() or "unknown-device"
        return f"{devname}_{instance}" if DEV_MULTIPLE_INSTANCES else devname
    base = cli_username or "unknown-user"
    return f"{base}_{instance}" if DEV_MULTIPLE_INSTANCES else base


def _get_autostart_command():
    installed_exe = LOCAL_APP_DIR / f"{APP_NAME}.exe"
    if installed_exe.exists():
        return f'"{installed_exe}"'
    elif getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    else:
        script = os.path.abspath(sys.argv[0])
        return f'"{sys.executable}" "{script}"'


def _create_ping_wav(
    duration_ms=400, freq1=784.0, freq2=1046.5, volume=0.4, sample_rate=44100
):
    nframes = int(sample_rate * (duration_ms / 1000.0))
    amplitude = int(32767 * max(0.0, min(1.0, volume)))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp_name = tmp.name
    tmp.close()

    with wave.open(tmp_name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        for i in range(nframes):
            t = i / sample_rate
            progress = t / (duration_ms / 1000.0)

            bell_env = math.exp(-4.0 * progress)
            soft_attack = 1.0 - math.exp(-8.0 * progress)
            env = bell_env * soft_attack

            wave1 = math.sin(2.0 * math.pi * freq1 * t)
            wave2 = math.sin(2.0 * math.pi * freq2 * t) * 0.3
            wave3 = math.sin(2.0 * math.pi * (freq1 * 0.5) * t) * 0.2

            combined = (wave1 + wave2 + wave3) / 1.5
            sample = int(amplitude * env * combined)
            wf.writeframes(struct.pack("<h", sample))

    def _cleanup(path=tmp_name):
        try:
            os.unlink(path)
        except Exception:
            pass

    atexit.register(_cleanup)
    return tmp_name


class RoundedOverlay(QtWidgets.QWidget):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        radius: int = WINDOW_RADIUS,
        opacity: int = 120,
    ):
        super().__init__(parent)
        self._radius = radius
        self._alpha = opacity
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(QtCore.Qt.Widget)
        if parent:
            self.setGeometry(parent.rect())
            self.show()
            self.raise_()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = QtGui.QColor(0, 0, 0, self._alpha)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(color))
        rect = self.rect()
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()

    def resizeEvent(self, event):
        self.update()
        super().resizeEvent(event)


class SoundPlayer:
    def __init__(self, parent=None, wav_path=None):
        self.parent = parent
        self.wav_path = wav_path or _create_ping_wav()
        self._qsound = None
        if QSoundEffect is not None:
            try:
                self._qsound = QSoundEffect(parent)
                url = QtCore.QUrl.fromLocalFile(self.wav_path)
                self._qsound.setSource(url)
                self._qsound.setLoopCount(1)
                try:
                    self._qsound.setVolume(0.4)
                except Exception:
                    pass
            except Exception:
                self._qsound = None

    def play(self):
        if self._qsound is not None:
            try:
                self._qsound.play()
                return
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                import winsound

                winsound.PlaySound(
                    self.wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC
                )
                return
            except Exception:
                pass

        return


class NonClosingMenu(QtWidgets.QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event):
        widget = self.childAt(event.pos())
        if widget and (
            isinstance(widget, QtWidgets.QLineEdit)
            or widget.findChild(QtWidgets.QLineEdit)
        ):
            event.accept()
            return
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        pass

    def hideEvent(self, event):
        if not self.property("prevent_hide"):
            super().hideEvent(event)


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.settings = QtCore.QSettings()

        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            QtWidgets.QMessageBox.critical(
                None, "System Tray", "System tray not available"
            )
            sys.exit(1)

        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self._on_save_timer_timeout)

        self.create_icon()
        self.setup_context_menu()
        self.setup_signals()
        self.setup_tooltip()
        self.setup_autostart()

    def eventFilter(self, obj, event):
        if obj == getattr(self, "server_input", None):
            if event.type() == QtCore.QEvent.KeyPress:
                key = event.key()
                if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                    self._save_timer.stop()
                    self.save_server_url(self.server_input.text())
                    return True
            return False

        if obj == getattr(self, "menu", None):
            if event.type() == QtCore.QEvent.KeyPress:
                key = event.key()
                if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                    return True
            return False

        return super().eventFilter(obj, event)

    def create_icon(self):
        icon_path = resource_path("app_icon.png")
        if os.path.exists(icon_path):
            try:
                pixmap = QtGui.QPixmap(icon_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        64,
                        64,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                    self.setIcon(QtGui.QIcon(pixmap))
                    return
            except Exception as e:
                print(f"Failed to load external icon: {e}")

        size = 64
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        gradient = QtGui.QRadialGradient(size // 2, size // 2, size // 2)
        gradient.setColorAt(0, QtGui.QColor(COLORS["--accent"]))
        gradient.setColorAt(1, QtGui.QColor(COLORS["--primary"]))

        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(8, 8, size - 16, size - 16)

        painter.setBrush(QtGui.QColor(COLORS["--background"]))
        painter.drawEllipse(size // 2 - 6, size // 2 - 6, 12, 12)

        painter.end()
        self.setIcon(QtGui.QIcon(pixmap))

    def setup_context_menu(self):
        self.menu = QtWidgets.QMenu(self.parent)
        self.apply_menu_styling()

        self.menu.setFocusPolicy(QtCore.Qt.NoFocus)
        self.menu.setSeparatorsCollapsible(False)
        self.menu.setActiveAction(None)

        self.menu.installEventFilter(self)

        show_action = QtWidgets.QAction("Toggle Window", self.menu)
        show_action.triggered.connect(self.toggle_window_visibility)
        self.menu.addAction(show_action)

        server_action = QtWidgets.QWidgetAction(self.menu)
        server_widget = QtWidgets.QWidget()
        server_layout = QtWidgets.QHBoxLayout(server_widget)
        server_layout.setContentsMargins(8, 6, 8, 6)

        self.server_input = QtWidgets.QLineEdit()
        self.server_input.setPlaceholderText("Server URL")
        self.server_input.setText(self.settings.value("server_url", DEFAULT_SERVER))
        self.server_input.setFixedWidth(420)
        self.server_input.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.server_input.installEventFilter(self)
        self.server_input.textChanged.connect(self._on_server_text_changed)

        self.server_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS["--dim-background"]};
                color: {COLORS["--text"]};
                border: 0px solid {COLORS["--secondary"]};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                min-width: 160px;
                font-family: {FONT_FAMILY};
            }}
            QLineEdit:focus {{
                border-color: {COLORS["--secondary"]};
                background-color: {COLORS["--dim-background"]};
            }}
            QLineEdit::placeholder {{
                color: {COLORS["--muted"]};
            }}
        """)

        server_layout.addWidget(self.server_input)
        server_action.setDefaultWidget(server_widget)
        self.menu.addAction(server_action)

        self.startup_action = QtWidgets.QAction("Start with system", self.menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(
            self.settings.value("autostart", True, type=bool)
        )
        self.startup_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.startup_action)

        exit_action = QtWidgets.QAction("Exit", self.menu)
        exit_action.triggered.connect(self.exit_application)
        self.menu.addAction(exit_action)

        self.setContextMenu(self.menu)

    def _on_server_text_changed(self, text):
        self._save_timer.start()

    def _on_save_timer_timeout(self):
        if getattr(self, "server_input", None) is not None:
            self.save_server_url(self.server_input.text())

    def apply_menu_styling(self):
        self.menu.setWindowFlags(
            self.menu.windowFlags()
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.NoDropShadowWindowHint
        )
        self.menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS["--dim-background"]};
                color: {COLORS["--text"]};
                border: 1px solid {COLORS["--primary"]};
                border-radius: 12px;
                padding: 6px 4px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                margin: 0;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 6px;
                margin: 3px 6px;
                border: 1px solid {COLORS["--primary"]};
                background-color: {COLORS["--background"]};
            }}
            QMenu::item:selected {{
                border: 1px dotted {COLORS["--primary"]};
                background-color: {COLORS["--dim-background"]};
                color: {COLORS["--text"]};
            }}
            QMenu::indicator {{
                width: 4px;
                height: 4px;
                left: 10px;
                margin: 2px 4px;
                border: 1px solid {COLORS["--accent"]};
                background: transparent;
                border-radius: 16px;
            }}

            QMenu::indicator:checked {{
                border: 1px solid {COLORS["--accent"]};
                width: 4px;
                height: 4px;
                left: 10px;
                background: {COLORS["--success"]};
                border-radius: 16px;
            }}

            QLineEdit {{
                background-color: {COLORS["--dim-background"]};
                color: {COLORS["--highlight"]};
                border: 1px solid {COLORS["--secondary"]};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: {FONT_FAMILY};
                min-width: 200px;
                selection-background-color: {COLORS["--background"]};
            }}
            QLineEdit:focus {{
                border-color: {COLORS["--highlight"]};
                background-color: {COLORS["--secondary"]};
            }}
            QLineEdit::placeholder {{
                color: {COLORS["--muted"]};
            }}
        """)

    def setup_signals(self):
        self.activated.connect(self.on_tray_activated)

    def setup_tooltip(self):
        self.setToolTip(f"{APP_NAME}")

    def setup_autostart(self):
        autostart_enabled = self.settings.value("autostart", True, type=bool)
        self.set_autostart(autostart_enabled)

    def set_autostart(self, enable):
        if sys.platform == "win32":
            self._set_autostart_windows(enable)
        elif sys.platform == "darwin":
            self._set_autostart_macos(enable)
        else:
            self._set_autostart_linux(enable)

    def _set_autostart_windows(self, enable):
        try:
            import winreg

            key = winreg.HKEY_CURRENT_USER
            subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"

            if enable:
                app_path = _get_autostart_command()

                try:
                    with winreg.OpenKey(
                        key, subkey, 0, winreg.KEY_SET_VALUE
                    ) as reg_key:
                        winreg.SetValueEx(reg_key, APP_NAME, 0, winreg.REG_SZ, app_path)
                    print(f"Autostart enabled: {app_path}")
                except Exception as e:
                    print(f"Failed to enable autostart: {e}")
            else:
                try:
                    with winreg.OpenKey(
                        key, subkey, 0, winreg.KEY_SET_VALUE
                    ) as reg_key:
                        winreg.DeleteValue(reg_key, APP_NAME)
                    print("Autostart disabled")
                except FileNotFoundError:
                    pass

        except ImportError:
            print("winreg not available")

    def _set_autostart_macos(self, enable):
        print(f"macOS autostart would be {'enabled' if enable else 'disabled'}")

    def _set_autostart_linux(self, enable):
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(autostart_dir, f"{APP_NAME}.desktop")

        if enable:
            os.makedirs(autostart_dir, exist_ok=True)
            app_path = _get_autostart_command()

            desktop_content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={app_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            try:
                with open(desktop_file, "w") as f:
                    f.write(desktop_content)
                print(f"Autostart enabled: {desktop_file}")
            except Exception as e:
                print(f"Failed to enable autostart: {e}")
        else:
            try:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
                print("Autostart disabled")
            except Exception as e:
                print(f"Failed to disable autostart: {e}")

    def save_server_url(self, url):
        self.settings.setValue("server_url", url.strip())
        print(f"Server URL saved: {url.strip()}")

    def get_server_url(self):
        return self.settings.value("server_url", DEFAULT_SERVER)

    def toggle_autostart(self, enabled):
        self.settings.setValue("autostart", enabled)
        self.set_autostart(enabled)

    def on_tray_activated(self, reason):
        if reason in (
            QtWidgets.QSystemTrayIcon.DoubleClick,
            QtWidgets.QSystemTrayIcon.Trigger,
        ):
            self.toggle_window_visibility()

    def toggle_window_visibility(self):
        if self.parent and hasattr(self.parent, "isVisible"):
            if self.parent.isVisible():
                self.parent.hide()
            else:
                self.parent.show()
                self.parent.raise_()
                self.parent.activateWindow()

    def exit_application(self):
        if self.parent:
            self.parent.close()
        QtWidgets.QApplication.quit()


class PingClient:
    def __init__(self, server, username, uid, gui_signals):
        self.server = server.rstrip("/")
        self.username = username
        self.uid = uid
        self.token = None
        self.token_expiry = 0.0
        self._stop_event = threading.Event()
        self.gui_signals = gui_signals
        self.available_users = set()
        self.user_history = set()

    def login(self):
        resp = requests.post(
            f"{self.server}/login",
            json={"username": self.username, "uid": self.uid},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["token"]
        self.token_expiry = time.time() + int(data.get("expires_in", 3600)) - 5
        return data

    def ensure_token(self):
        if not self.token or time.time() >= self.token_expiry:
            for attempt in range(4):
                try:
                    self.login()
                    return self.token
                except RequestException:
                    time.sleep(0.5 * (2**attempt))
            raise RuntimeError("Failed to obtain token")
        return self.token

    def send_ping(self, target):
        try:
            token = self.ensure_token()
        except Exception as e:
            return None, f"Auth error: {e}"

        if target and target != self.username:
            self.user_history.add(target)
            self.gui_signals.user_history_updated.emit()

        try:
            resp = requests.post(
                f"{self.server}/ping",
                json={"to": target},
                headers={"Authorization": f"Bearer {token}"},
                timeout=DEFAULT_TIMEOUT,
            )
            return resp.status_code, resp.json() if resp.text else resp.text
        except RequestException as e:
            return None, str(e)

    async def _ws_run(self):
        scheme = "wss" if self.server.lower().startswith("https") else "ws"
        host = self.server.split("://", 1)[-1]
        url = f"{scheme}://{host}/ws"
        attempt = 0

        while not self._stop_event.is_set():
            try:
                token = self.ensure_token()
                ws_url = f"{url}?token={token}"

                async with websockets.connect(
                    ws_url, ping_interval=20, ping_timeout=10
                ) as ws:
                    attempt = 0
                    self.gui_signals.ws_connected.emit()

                    while not self._stop_event.is_set():
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=60)
                            print(msg)
                            parsed = json.loads(msg)
                            if parsed.get("type") in ("ping", "queued_ping"):
                                self.gui_signals.ping_received.emit(
                                    parsed.get("from"),
                                    float(parsed.get("ts", time.time())),
                                )
                            elif parsed.get("type") in ("clientlist"):
                                clients = parsed.get("clients", [])
                                self.available_users = set(clients)
                                self.gui_signals.user_list_updated.emit()
                                print(clients)
                        except asyncio.TimeoutError:
                            try:
                                await ws.send("keepalive")
                            except Exception:
                                break
                        except websockets.ConnectionClosed:
                            print("CLOSED!")
                            break

            except Exception:
                self.gui_signals.ws_disconnected.emit()
                attempt += 1
                await asyncio.sleep(min(30, 0.5 * (2**attempt)))

    def start(self):
        try:
            self.ensure_token()
        except Exception:
            pass
        self._stop_event.clear()
        self._ws_thread = threading.Thread(
            target=lambda: asyncio.run(self._ws_run()), daemon=True
        )
        self._ws_thread.start()

    def stop(self):
        self._stop_event.set()


class GuiSignals(QtCore.QObject):
    ws_connected = QtCore.pyqtSignal()
    ws_disconnected = QtCore.pyqtSignal()
    ping_received = QtCore.pyqtSignal(str, float)
    error = QtCore.pyqtSignal(str)
    info = QtCore.pyqtSignal(str)
    warning = QtCore.pyqtSignal(str)
    success = QtCore.pyqtSignal(str)
    user_list_updated = QtCore.pyqtSignal()
    user_history_updated = QtCore.pyqtSignal()


class ConnectionIndicator(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._connected = False
        self._pulse_value = 0.3

        self._pulse_animation = QtCore.QPropertyAnimation(self, b"pulse_value")
        self._pulse_animation.setDuration(1500)
        self._pulse_animation.setLoopCount(-1)
        self._pulse_animation.setKeyValueAt(0, 0.3)
        self._pulse_animation.setKeyValueAt(0.5, 1.0)
        self._pulse_animation.setKeyValueAt(1, 0.3)

    pulse_value = QtCore.pyqtProperty(
        float,
        lambda self: self._pulse_value,
        lambda self, value: setattr(self, "_pulse_value", value) or self.update(),
    )

    def set_connected(self, connected):
        self._connected = connected
        if connected:
            self._pulse_animation.start()
        else:
            self._pulse_animation.stop()
            self._pulse_value = 0.3
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        center_x = self.width() // 2
        center_y = self.height() // 2

        if self._connected:
            color = QtGui.QColor(COLORS["--success"])
            color.setAlphaF(self._pulse_value)
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center_x - 10, center_y - 10, 20, 20)

            painter.setBrush(QtGui.QColor(COLORS["--success"]))
            painter.drawEllipse(center_x - 5, center_y - 5, 10, 10)
        else:
            painter.setBrush(QtGui.QColor(COLORS["--error"]))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center_x - 10, center_y - 10, 20, 20)


class PingNotification(QtWidgets.QWidget):
    def __init__(self, parent, sender, ts):
        super().__init__(
            parent,
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool,
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(260, 110)

        self.overlay = RoundedOverlay(self, radius=14, opacity=200)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("Incoming Ping")
        title.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-weight: 600; font-size: 15px; color: {COLORS['--text']};"
        )
        layout.addWidget(title)

        sender_layout = QtWidgets.QHBoxLayout()
        from_label = QtWidgets.QLabel("From:")
        from_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; color: {COLORS['--muted']}; font-size: 12px;"
        )
        sender_layout.addWidget(from_label)

        sender_name = QtWidgets.QLabel(sender)
        sender_name.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-weight: 600; color: {COLORS['--text']}; font-size: 13px;"
        )
        sender_layout.addWidget(sender_name)
        sender_layout.addStretch()
        layout.addLayout(sender_layout)

        time_label = QtWidgets.QLabel(time.strftime("%H:%M:%S", time.localtime(ts)))
        time_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; color: {COLORS['--muted']}; font-size: 11px;"
        )
        time_label.setAlignment(QtCore.Qt.AlignRight)
        layout.addWidget(time_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS["--primary"]};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS["--highlight"]};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        self.enter_anim = QtCore.QPropertyAnimation(
            self, b"windowOpacity", duration=300, startValue=0.0, endValue=1.0
        )
        self.progress_anim = QtCore.QPropertyAnimation(
            self.progress_bar,
            b"value",
            duration=PING_POPUP_DURATION,
            startValue=100,
            endValue=0,
        )

        self.close_timer = QtCore.QTimer(singleShot=True, timeout=self.close)

    def showEvent(self, event):
        self.enter_anim.start()
        self.progress_anim.start()
        self.close_timer.start(PING_POPUP_DURATION)

    def resizeEvent(self, event):
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        self.close()


class FocusAwareLineEdit(QtWidgets.QLineEdit):
    focusIn = QtCore.pyqtSignal()
    focusOut = QtCore.pyqtSignal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focusIn.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusOut.emit()


class RotatingButton(QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rotation = 0
        self._animation = QtCore.QVariantAnimation()
        self._animation.valueChanged.connect(self.set_rotation)

    def get_rotation(self):
        return self._rotation

    def set_rotation(self, value):
        self._rotation = value
        self.update()

    rotation = QtCore.pyqtProperty(float, get_rotation, set_rotation)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        opt = QtWidgets.QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawControl(
            QtWidgets.QStyle.CE_PushButtonBevel, opt, painter, self
        )

        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._rotation)

        font = self.font()
        font_metrics = QtGui.QFontMetrics(font)
        text_width = font_metrics.horizontalAdvance(self.text())
        text_height = font_metrics.height()

        painter.setFont(font)
        painter.setPen(QtGui.QPen(self.palette().buttonText().color()))
        painter.drawText(int(-text_width / 2), int(text_height / 4), self.text())
        painter.restore()


class UserComboBox(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.text_input = FocusAwareLineEdit(
            placeholderText="Enter username...",
            minimumHeight=36,
            styleSheet=f"""
                QLineEdit {{
                    font-family: {FONT_FAMILY};
                    background-color: {COLORS["--secondary"]};
                    border: 1px solid {COLORS["--primary"]};
                    border-top-left-radius: 10px;
                    border-bottom-left-radius: 10px;
                    border-top-right-radius: 0px;
                    border-bottom-right-radius: 0px;
                    border-right: none;
                    padding: 8px 12px;
                    font-size: 12px;
                    color: {COLORS["--text"]};
                    selection-background-color: {COLORS["--accent"]};
                }}
                QLineEdit:focus {{
                    border-color: {COLORS["--highlight"]};
                    border-right: none;
                    background-color: {COLORS["--secondary"]};
                }}
                QLineEdit::placeholder {{
                    color: {COLORS["--muted"]};
                }}
            """,
        )
        layout.addWidget(self.text_input)

        self.dropdown_button = RotatingButton(
            "▼",
            minimumHeight=36,
            minimumWidth=36,
            maximumWidth=36,
            cursor=QtGui.QCursor(QtCore.Qt.PointingHandCursor),
            styleSheet=f"""
                QPushButton {{
                    font-family: {FONT_FAMILY};
                    background-color: {COLORS["--secondary"]};
                    color: {COLORS["--text"]};
                    border: 1px solid {COLORS["--primary"]};
                    border-top-left-radius: 0px;
                    border-bottom-left-radius: 0px;
                    border-top-right-radius: 10px;
                    border-bottom-right-radius: 10px;
                    border-left: none;
                    font-size: 10px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS["--accent"]};
                }}
                QPushButton:pressed {{
                    background-color: {COLORS["--primary"]};
                }}
            """,
        )
        layout.addWidget(self.dropdown_button)

        self.rotation_animation = QtCore.QPropertyAnimation(
            self.dropdown_button, b"rotation"
        )
        self.rotation_animation.setDuration(200)
        self.rotation_animation.setStartValue(0)
        self.rotation_animation.setEndValue(-90)

        self.text_input.focusIn.connect(self._on_input_focus_in)
        self.text_input.focusOut.connect(self._on_input_focus_out)

        self.dropdown_menu = QtWidgets.QMenu(self)
        self.dropdown_menu.setWindowFlags(
            self.dropdown_menu.windowFlags()
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.NoDropShadowWindowHint
        )
        self.dropdown_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._setup_menu_styling()

        self.dropdown_button.clicked.connect(self.show_dropdown)

    def _setup_menu_styling(self):
        self.dropdown_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS["--background"]};
                color: {COLORS["--text"]};
                border: 1px solid {COLORS["--primary"]};
                border-radius: 14px;
                padding: 8px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                margin: 0px;
            }}
            QMenu::item {{
                padding: 8px 14px;
                border-radius: 8px;
                margin: 2px 2px;
                font-family: {FONT_FAMILY};
            }}
            QMenu::item:selected {{
                background-color: {COLORS["--accent"]};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {COLORS["--primary"]};
                margin: 6px 8px;
                border-radius: 1px;
            }}
            QMenu::section {{
                background-color: {COLORS["--secondary"]};
                color: {COLORS["--muted"]};
                font-weight: bold;
                font-size: 11px;
                padding: 8px 12px 6px 12px;
                border: none;
                margin: 0px;
                border-radius: 6px;
                font-family: {FONT_FAMILY};
            }}
        """)

    def _on_input_focus_in(self):
        self.dropdown_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {FONT_FAMILY};
                background-color: {COLORS["--secondary"]};
                color: {COLORS["--text"]};
                border: 1px solid {COLORS["--highlight"]};
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                border-left: none;
                font-size: 10px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["--accent"]};
            }}
            QPushButton:pressed {{
                background-color: {COLORS["--primary"]};
            }}
        """)

    def _on_input_focus_out(self):
        self.dropdown_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {FONT_FAMILY};
                background-color: {COLORS["--secondary"]};
                color: {COLORS["--text"]};
                border: 1px solid {COLORS["--primary"]};
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                border-left: none;
                font-size: 10px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["--accent"]};
            }}
            QPushButton:pressed {{
                background-color: {COLORS["--primary"]};
            }}
        """)

    def show_dropdown(self):
        self._rebuild_dropdown_menu()
        pos = self.dropdown_button.mapToGlobal(
            QtCore.QPoint(0, self.dropdown_button.height())
        )

        self.rotation_animation.setDirection(QtCore.QAbstractAnimation.Forward)
        self.rotation_animation.start()

        self.dropdown_menu.aboutToHide.connect(self._on_menu_hide)
        self.dropdown_menu.popup(pos)

    def _on_menu_hide(self):
        self.rotation_animation.setDirection(QtCore.QAbstractAnimation.Backward)
        self.rotation_animation.start()
        self.dropdown_menu.aboutToHide.disconnect(self._on_menu_hide)

    def _add_section(self, title):
        label = QtWidgets.QLabel(title)
        label.setStyleSheet("""
            padding-left: 8px;
            color: gray;
            font-weight: bold;
            font-style: italic;
            font-variant: small-caps;
            font-family: Arial, sans-serif;
            font-size: 8px;
            text-transform: uppercase;
            border: none;
            background: transparent;
        """)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        widget_action = QtWidgets.QWidgetAction(self.dropdown_menu)
        widget_action.setDefaultWidget(label)
        self.dropdown_menu.addAction(widget_action)

    def _rebuild_dropdown_menu(self):
        self.dropdown_menu.clear()

        if hasattr(self, "_online_users") and self._online_users:
            self._add_section("Online")
            for user in sorted(self._online_users):
                action = QtWidgets.QAction(user, self.dropdown_menu)
                action.triggered.connect(
                    lambda checked, u=user: self.text_input.setText(u)
                )
                self.dropdown_menu.addAction(action)
            self.dropdown_menu.addSeparator()
        else:
            no_action = QtWidgets.QAction("No online users", self.dropdown_menu)
            no_action.setEnabled(False)
            self.dropdown_menu.addAction(no_action)
            self.dropdown_menu.addSeparator()

        if hasattr(self, "_recent_users") and self._recent_users:
            self._add_section("Recents")
            for user in sorted(self._recent_users):
                action = QtWidgets.QAction(user, self.dropdown_menu)
                action.triggered.connect(
                    lambda checked, u=user: self.text_input.setText(u)
                )
                self.dropdown_menu.addAction(action)
        else:
            no_recent = QtWidgets.QAction("No recent pings", self.dropdown_menu)
            no_recent.setEnabled(False)
            self.dropdown_menu.addAction(no_recent)

    def set_online_users(self, users):
        self._online_users = users

    def set_recent_users(self, users):
        self._recent_users = users

    def text(self):
        return self.text_input.text().strip()

    def setText(self, text):
        self.text_input.setText(text)


class PingWindow(QtWidgets.QWidget):
    def __init__(self, server, username, uid):
        super().__init__()
        self.server = server
        self.username = username
        self.uid = uid

        self.setup_window()
        self.setup_ui()
        self._drag_pos = None

        self.sound_player = SoundPlayer(parent=self)

        self.tray_icon = SystemTrayIcon(self)
        self.tray_icon.show()

        QtWidgets.QApplication.setQuitOnLastWindowClosed(False)

        QtCore.QTimer.singleShot(2000, lambda: check_updates_in_background(self))

    @QtCore.pyqtSlot(str, str)
    def show_update_dialog(self, latest_version, download_url):
        show_update_message(self, latest_version, download_url)

    def setup_window(self):
        self.resize(WINDOW_SIZE, WINDOW_SIZE)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 0);")

        self.setWindowTitle(f"{APP_NAME} - {self.username}")

        self.overlay = RoundedOverlay(self, radius=WINDOW_RADIUS, opacity=200)

    def setup_ui(self):
        self.client = None
        self.signals = GuiSignals()

        self._central = QtWidgets.QWidget(
            self,
            styleSheet=f"""
            background-color: {COLORS["--background"]};
            border-radius: {WINDOW_RADIUS}px;
            border: 1px solid {COLORS["--primary"]};
            font-family: {FONT_FAMILY};
        """,
        )
        self._central.setGeometry(self.rect())

        layout = QtWidgets.QVBoxLayout(self._central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        status_widget = QtWidgets.QWidget(
            styleSheet="background: transparent; border: none;"
        )
        status_layout = QtWidgets.QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(10)
        status_layout.setAlignment(QtCore.Qt.AlignCenter)

        self.status_indicator = ConnectionIndicator()
        status_layout.addWidget(self.status_indicator)

        self.username_label = QtWidgets.QLabel(
            f"@{self.username}",
            styleSheet=f"""
                font-family: {FONT_FAMILY};
                color: {COLORS["--text"]};
                font-size: 13px;
                font-weight: 500;
                background: transparent;
                border: none;
                padding: 2px 0px;
            """,
        )
        status_layout.addWidget(self.username_label)

        layout.addWidget(status_widget)

        self.target_combo = UserComboBox()
        layout.addWidget(self.target_combo)

        self.ping_button = QtWidgets.QPushButton(
            "SEND PING",
            enabled=False,
            cursor=QtGui.QCursor(QtCore.Qt.PointingHandCursor),
            minimumHeight=38,
            styleSheet=f"""
                QPushButton {{
                    font-family: {FONT_FAMILY};
                    background-color: {COLORS["--accent"]};
                    color: {COLORS["--text"]};
                    font-weight: 600;
                    font-size: 13px;
                    border-radius: 10px;
                    padding: 10px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {COLORS["--highlight"]};
                }}
                QPushButton:pressed {{
                    background-color: {COLORS["--primary"]};
                }}
                QPushButton:disabled {{
                    background-color: {COLORS["--secondary"]};
                    color: {COLORS["--muted"]};
                }}
            """,
        )
        layout.addWidget(self.ping_button)

        self.setup_signals()

    def setup_signals(self):
        self.signals.ws_connected.connect(lambda: self._update_status(True))
        self.signals.ws_disconnected.connect(lambda: self._update_status(False))
        self.signals.ping_received.connect(self._on_ping_received)
        self.signals.error.connect(
            lambda msg: self._show_message("Error", msg, COLORS["--error"])
        )
        self.signals.warning.connect(
            lambda msg: self._show_message("Warning", msg, COLORS["--muted"])
        )
        self.signals.info.connect(
            lambda msg: self._show_message("Info", msg, COLORS["--muted"])
        )
        self.signals.success.connect(
            lambda msg: self._show_message("Success", msg, COLORS["--success"])
        )
        self.signals.user_list_updated.connect(self._update_user_list)
        self.signals.user_history_updated.connect(self._update_user_history)
        self.ping_button.clicked.connect(self._send_ping)

    def resizeEvent(self, event):
        self._central.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)

    def _update_status(self, online):
        self.status_indicator.set_connected(online)
        self.ping_button.setEnabled(online)

    def _update_user_list(self):
        if self.client:
            self.target_combo.set_online_users(self.client.available_users)

    def _update_user_history(self):
        if self.client:
            self.target_combo.set_recent_users(self.client.user_history)

    def _send_ping(self):
        target = self.target_combo.text()
        if not target:
            self._show_message(
                "Warning", "Please enter a target username", COLORS["--muted"]
            )
            return

        original_text = self.ping_button.text()
        self.ping_button.setText("SENDING...")
        self.ping_button.setEnabled(False)
        QtCore.QTimer.singleShot(
            100, lambda: self._actually_send_ping(target, original_text)
        )

    def _actually_send_ping(self, target, original_text):
        def worker():
            code, data = self.client.send_ping(target)
            QtCore.QMetaObject.invokeMethod(
                self,
                "_ping_complete",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(int, code if code is not None else 0),
                QtCore.Q_ARG(str, str(data)),
                QtCore.Q_ARG(str, original_text),
            )

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.pyqtSlot(int, str, str)
    def _ping_complete(self, code, data, original_text):
        self.ping_button.setText(original_text)
        self.ping_button.setEnabled(True)

        if code == 0:
            self.signals.error.emit(f"Network error: {data}")
        elif code == 200:
            self.signals.success.emit("Ping delivered successfully")
        elif code == 202:
            self.signals.info.emit("Target offline - ping queued")
        else:
            self.signals.warning.emit(f"Server response {code}: {data}")

    def _show_message(self, title, text, color):
        popup = QtWidgets.QWidget(
            self,
            QtCore.Qt.FramelessWindowHint,
            styleSheet=f"""
            QWidget {{
                background-color: {COLORS["--background"]};
                border-radius: 14px;
                border: 1px solid {color};
                font-family: {FONT_FAMILY};
            }}
        """,
        )

        popup_overlay = RoundedOverlay(popup, radius=14, opacity=200)

        layout = QtWidgets.QVBoxLayout(popup)
        title_label = QtWidgets.QLabel(
            title,
            styleSheet=f"color: {color}; font-size: 13px; font-weight: 600; font-family: {FONT_FAMILY};",
        )
        text_label = QtWidgets.QLabel(
            text,
            styleSheet=f"color: {COLORS['--text']}; font-size: 12px; font-family: {FONT_FAMILY};",
        )
        layout.addWidget(title_label)
        layout.addWidget(text_label)

        btn = QtWidgets.QPushButton(
            "OK",
            clicked=popup.close,
            styleSheet=f"""
            QPushButton {{
                font-family: {FONT_FAMILY};
                background-color: {color};
                color: {COLORS["--text"]};
                border: none;
                padding: 6px 12px;
                border-radius: 8px;
                font-size: 11px;
                margin-top: 8px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """,
        )
        layout.addWidget(btn)

        popup.resize(200, 120)
        popup.move(self.geometry().center() - popup.rect().center())
        popup.show()

        def resize_popup():
            popup_overlay.setGeometry(popup.rect())

        popup.resizeEvent = lambda event: resize_popup()
        resize_popup()

    def _on_ping_received(self, sender, ts):
        self.sound_player.play()

        popup = PingNotification(self, sender, ts)
        screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        popup.move(screen_geo.right() - popup.width() - 20, screen_geo.top() + 20)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def attach_client(self, client):
        self.client = client

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            if hasattr(self, "client") and self.client:
                self.client.stop()
            event.accept()


def main():
    print(f"{APP_NAME} v{APP_VERSION}")

    is_update, latest_version, download_url, error = check_for_updates()
    if error:
        print(f"Update check failed: {error}")
    elif is_update:
        print(f"Update available: {latest_version} (current: {APP_VERSION})")
        print(f"Download at: {download_url}")
    else:
        print(f"Running latest version: {APP_VERSION}")

    if getattr(sys, "frozen", False) or (
        len(sys.argv) > 0 and sys.argv[0].endswith(".exe")
    ):
        print("Performing automatic self-installation...")
        self_install()
    else:
        print("Running as Python script, skipping self-installation")

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--server",
        default=None,
        help=f"Server URL (default from settings or {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help="Username (default: auto-generated from device name)",
    )
    parser.add_argument(
        "--instance",
        type=int,
        default=DEFAULT_INSTANCE,
        help=f"Instance ID (default: {DEFAULT_INSTANCE})",
    )
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain(ORGANIZATION_DOMAIN)

    settings = QtCore.QSettings()
    persisted_server = settings.value("server_url", DEFAULT_SERVER)
    startup_enabled = settings.value("startup_enabled", True, type=bool)
    server_to_use = args.server or persisted_server
    if args.server:
        settings.setValue("server_url", server_to_use)
    if server_to_use and not server_to_use.endswith("/"):
        server_to_use = server_to_use + "/"

    username = derive_username(args.username, args.instance)
    uid = generate_uid()

    print(f"Starting {APP_NAME}")
    print(f"  Username: {username}")
    print(f"  User ID: {uid}")
    print(f"  Server: {server_to_use}")
    print(f"  Instance: {args.instance}")
    print(f"  Autostart enabled: {startup_enabled}")

    app.setQuitOnLastWindowClosed(False)

    font = QtGui.QFont("Segoe UI", 10)
    app.setFont(font)

    window = PingWindow(server_to_use, username, uid)
    client = PingClient(server_to_use, username, uid, window.signals)
    window.attach_client(client)

    QtCore.QTimer().start(100)

    threading.Thread(target=client.start, daemon=True).start()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
