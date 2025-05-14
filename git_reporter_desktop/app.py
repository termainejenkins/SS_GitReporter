import sys
import os
import json
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMenuBar, QAction, QSystemTrayIcon, QStyle, QMenu,
    QDialog, QLineEdit, QComboBox, QFormLayout, QMessageBox, QListWidgetItem, QTextEdit, QFileDialog,
    QTimeEdit, QCheckBox, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
import shutil
import platform
import threading
import datetime

# Import GitMonitor and DiscordClient from the CLI codebase
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from git_reporter.monitor import GitMonitor
from git_reporter.discord_client import DiscordClient

# --- Roadmap ---
# - Project/webhook management dialogs
# - System tray integration
# - Background monitoring
# - Log viewer
# - Config persistence
# - Message formatting options (commit messages, short interpretations, changelog, daily summary)

MESSAGE_FORMATS = [
    'Raw commit messages',
    'Short interpretation',
    'Changelog style',
    'Daily summary'
]

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'desktop_config.json')
SETTINGS_FILE = CONFIG_FILE  # Use the same config file for simplicity

MONITOR_INTERVAL_SECONDS = 60  # Default check interval (can be made configurable)

class MonitorWorker(QThread):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, projects):
        super().__init__()
        self.projects = projects
        self.running = False
        self.last_commit_hashes = {}  # Track last commit per project

    def run(self):
        self.running = True
        self.log_signal.emit('Background monitoring started.')
        while self.running:
            for project in self.projects:
                name = project.get('name', 'Unknown')
                path = project.get('path', '')
                webhooks = project.get('webhooks', [])
                if not os.path.exists(path):
                    self.log_signal.emit(f"[ERROR] Project path does not exist: {path}")
                    continue
                try:
                    monitor = GitMonitor(path, ignored_files=[])
                except Exception as e:
                    self.log_signal.emit(f"[ERROR] Could not initialize GitMonitor for '{name}': {e}")
                    continue
                # Get latest commit hash
                latest_commit = monitor._run_git_command(['git', 'rev-parse', 'HEAD'])
                if not latest_commit:
                    self.log_signal.emit(f"[ERROR] Could not get latest commit for '{name}'")
                    continue
                last_hash = self.last_commit_hashes.get(path)
                if last_hash == latest_commit:
                    self.log_signal.emit(f"No new commits for '{name}'.")
                    continue
                self.last_commit_hashes[path] = latest_commit
                # Get changes and format message
                status, commits = monitor.get_changes()
                for wh in webhooks:
                    msg = self.format_message(wh['format'], name, status, commits)
                    self.log_signal.emit(f"Sending {wh['format']} report to {wh['webhook']} for '{name}'...")
                    try:
                        client = DiscordClient(wh['webhook'])
                        if client.send_message(msg):
                            self.log_signal.emit(f"[OK] Report sent to {wh['webhook']} for '{name}'.")
                        else:
                            self.log_signal.emit(f"[ERROR] Failed to send report to {wh['webhook']} for '{name}'.")
                    except Exception as e:
                        self.log_signal.emit(f"[ERROR] Exception sending to Discord: {e}")
            self.status_signal.emit('Monitoring cycle complete.')
            for _ in range(MONITOR_INTERVAL_SECONDS):
                if not self.running:
                    break
                time.sleep(1)
        self.log_signal.emit('Background monitoring stopped.')
        self.status_signal.emit('Monitoring stopped.')

    def stop(self):
        self.running = False

    def format_message(self, fmt, project_name, status, commits):
        if fmt == 'Raw commit messages':
            return f"**{project_name}**\nRecent Commits:\n```\n{commits or 'No recent commits.'}\n```"
        elif fmt == 'Short interpretation':
            if not commits:
                return f"**{project_name}**\nNo recent commits."
            first_line = commits.split('\n')[0]
            return f"**{project_name}**\nLatest: {first_line}"
        elif fmt == 'Changelog style':
            msg = [f"**{project_name} Changelog**"]
            if status:
                msg.append("Uncommitted Changes:\n```")
                msg.append(status)
                msg.append("```")
            if commits:
                msg.append("Recent Commits:\n```")
                msg.append(commits)
                msg.append("```")
            return '\n'.join(msg)
        elif fmt == 'Daily summary':
            # For now, just show the last 5 commits and status
            msg = [f"**{project_name} Daily Summary**"]
            if commits:
                msg.append("Commits today:\n```")
                msg.append(commits)
                msg.append("```")
            if status:
                msg.append("Uncommitted Changes:\n```")
                msg.append(status)
                msg.append("```")
            return '\n'.join(msg)
        else:
            return f"**{project_name}**\nNo data."

class WebhookDialog(QDialog):
    def __init__(self, parent=None, webhook=None, project_name=None, status=None, commits=None):
        super().__init__(parent)
        self.setWindowTitle('Add/Edit Webhook')
        self.setModal(True)
        layout = QFormLayout(self)

        self.webhook_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(MESSAGE_FORMATS)
        self.test_btn = QPushButton('Test')
        self.preview_btn = QPushButton('Preview')

        layout.addRow('Discord Webhook:', self.webhook_edit)
        layout.addRow('Message Format:', self.format_combo)
        layout.addRow(self.test_btn, self.preview_btn)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton('OK')
        self.cancel_btn = QPushButton('Cancel')
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.test_btn.clicked.connect(self.test_webhook)
        self.preview_btn.clicked.connect(self.preview_message)

        # For preview/test
        self.project_name = project_name or 'Project'
        self.status = status or 'No status.'
        self.commits = commits or 'No commits.'

        if webhook:
            self.webhook_edit.setText(webhook.get('webhook', ''))
            idx = self.format_combo.findText(webhook.get('format', MESSAGE_FORMATS[0]))
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)

    def get_data(self):
        return {
            'webhook': self.webhook_edit.text(),
            'format': self.format_combo.currentText()
        }

    def test_webhook(self):
        url = self.webhook_edit.text().strip()
        fmt = self.format_combo.currentText()
        msg = MonitorWorker.format_message(self, fmt, self.project_name, self.status, self.commits)
        if not url:
            QMessageBox.warning(self, 'Test Webhook', 'Please enter a webhook URL.')
            return
        try:
            client = DiscordClient(url)
            if client.send_message(msg):
                QMessageBox.information(self, 'Test Webhook', 'Test message sent successfully!')
            else:
                QMessageBox.critical(self, 'Test Webhook', 'Failed to send test message.')
        except Exception as e:
            QMessageBox.critical(self, 'Test Webhook', f'Error: {e}')

    def preview_message(self):
        fmt = self.format_combo.currentText()
        msg = MonitorWorker.format_message(self, fmt, self.project_name, self.status, self.commits)
        QMessageBox.information(self, 'Preview Message', msg)

class ProjectDialog(QDialog):
    def __init__(self, parent=None, project=None):
        super().__init__(parent)
        self.setWindowTitle('Add/Edit Project')
        self.setModal(True)
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.path_edit = QLineEdit()
        self.browse_btn = QPushButton('Browse')
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)
        form_layout.addRow('Project Name:', self.name_edit)
        form_layout.addRow('Project Path:', path_layout)
        layout.addLayout(form_layout)

        # Webhook management
        self.webhook_list = QListWidget()
        layout.addWidget(QLabel('Webhooks'))
        layout.addWidget(self.webhook_list)
        webhook_btn_layout = QHBoxLayout()
        self.add_webhook_btn = QPushButton('Add Webhook')
        self.edit_webhook_btn = QPushButton('Edit Webhook')
        self.remove_webhook_btn = QPushButton('Remove Webhook')
        webhook_btn_layout.addWidget(self.add_webhook_btn)
        webhook_btn_layout.addWidget(self.edit_webhook_btn)
        webhook_btn_layout.addWidget(self.remove_webhook_btn)
        layout.addLayout(webhook_btn_layout)

        # Dialog buttons
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton('OK')
        self.cancel_btn = QPushButton('Cancel')
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.webhooks = []
        self.add_webhook_btn.clicked.connect(self.open_add_webhook_dialog)
        self.edit_webhook_btn.clicked.connect(self.open_edit_webhook_dialog)
        self.remove_webhook_btn.clicked.connect(self.remove_selected_webhook)
        self.ok_btn.clicked.connect(self.validate_and_accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.browse_btn.clicked.connect(self.browse_path)

        if project:
            self.name_edit.setText(project.get('name', ''))
            self.path_edit.setText(project.get('path', ''))
            self.webhooks = [dict(wh) for wh in project.get('webhooks', [])]
            self.refresh_webhook_list()

    def browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Project Directory')
        if folder:
            self.path_edit.setText(folder)

    def validate_and_accept(self):
        import os
        path = self.path_edit.text().strip()
        if not os.path.isdir(path):
            QMessageBox.critical(self, 'Invalid Path', 'The specified path does not exist or is not a directory.')
            return
        if not os.path.isdir(os.path.join(path, '.git')):
            QMessageBox.critical(self, 'Invalid Git Repo', 'The specified path is not a valid git repository (missing .git folder).')
            return
        self.accept()

    def open_add_webhook_dialog(self):
        dialog = WebhookDialog(self, project_name=self.name_edit.text())
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.webhooks.append(data)
            self.refresh_webhook_list()

    def open_edit_webhook_dialog(self):
        row = self.webhook_list.currentRow()
        if row >= 0:
            wh = self.webhooks[row]
            dialog = WebhookDialog(self, webhook=wh, project_name=self.name_edit.text())
            if dialog.exec_() == QDialog.Accepted:
                self.webhooks[row] = dialog.get_data()
                self.refresh_webhook_list()
        else:
            QMessageBox.warning(self, 'Edit Webhook', 'Please select a webhook to edit.')

    def remove_selected_webhook(self):
        row = self.webhook_list.currentRow()
        if row >= 0:
            self.webhooks.pop(row)
            self.refresh_webhook_list()

    def refresh_webhook_list(self):
        self.webhook_list.clear()
        for wh in self.webhooks:
            self.webhook_list.addItem(f"{wh['webhook']} ({wh['format']})")

    def get_data(self):
        return {
            'name': self.name_edit.text(),
            'path': self.path_edit.text(),
            'webhooks': self.webhooks.copy()
        }

class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setModal(True)
        layout = QVBoxLayout(self)

        # Start with Windows
        self.start_with_windows_cb = QCheckBox('Start with Windows')
        layout.addWidget(self.start_with_windows_cb)

        # Scheduled times
        layout.addWidget(QLabel('Auto-Start Monitoring Schedule'))
        self.schedule_list = QListWidget()
        layout.addWidget(self.schedule_list)
        schedule_btn_layout = QHBoxLayout()
        self.add_time_btn = QPushButton('Add Time')
        self.remove_time_btn = QPushButton('Remove Time')
        schedule_btn_layout.addWidget(self.add_time_btn)
        schedule_btn_layout.addWidget(self.remove_time_btn)
        layout.addLayout(schedule_btn_layout)

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(self.button_box)

        self.add_time_btn.clicked.connect(self.add_time)
        self.remove_time_btn.clicked.connect(self.remove_selected_time)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.schedules = []  # List of dicts: {'time': 'HH:MM', 'days': [0,1,2,...]}
        if settings:
            self.start_with_windows_cb.setChecked(settings.get('start_with_windows', False))
            self.schedules = settings.get('schedules', [])
            self.refresh_schedule_list()

    def add_time(self):
        dialog = TimeDayDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.schedules.append(data)
            self.refresh_schedule_list()

    def remove_selected_time(self):
        row = self.schedule_list.currentRow()
        if row >= 0:
            self.schedules.pop(row)
            self.refresh_schedule_list()

    def refresh_schedule_list(self):
        self.schedule_list.clear()
        for sched in self.schedules:
            days = ','.join(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d] for d in sched['days'])
            self.schedule_list.addItem(f"{sched['time']} ({days})")

    def get_settings(self):
        return {
            'start_with_windows': self.start_with_windows_cb.isChecked(),
            'schedules': self.schedules
        }

class TimeDayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Scheduled Time')
        layout = QVBoxLayout(self)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat('HH:mm')
        layout.addWidget(QLabel('Time:'))
        layout.addWidget(self.time_edit)
        layout.addWidget(QLabel('Days of the Week:'))
        self.day_cbs = [QCheckBox(day) for day in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']]
        for cb in self.day_cbs:
            layout.addWidget(cb)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(btn_box)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

    def get_data(self):
        time_str = self.time_edit.time().toString('HH:mm')
        days = [i for i, cb in enumerate(self.day_cbs) if cb.isChecked()]
        return {'time': time_str, 'days': days}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('UE4 Git Reporter Desktop')
        self.setGeometry(100, 100, 800, 500)
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)))

        # In-memory project storage (persisted to config file)
        self.projects = []
        self.load_config()

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Project list and controls
        self.project_list = QListWidget()
        main_layout.addWidget(QLabel('Projects'))
        main_layout.addWidget(self.project_list)

        btn_layout = QHBoxLayout()
        self.add_project_btn = QPushButton('Add Project')
        self.edit_project_btn = QPushButton('Edit Project')
        self.remove_project_btn = QPushButton('Remove Project')
        self.start_monitor_btn = QPushButton('Start Monitoring')
        self.stop_monitor_btn = QPushButton('Stop Monitoring')
        self.stop_monitor_btn.setEnabled(False)
        btn_layout.addWidget(self.add_project_btn)
        btn_layout.addWidget(self.edit_project_btn)
        btn_layout.addWidget(self.remove_project_btn)
        btn_layout.addWidget(self.start_monitor_btn)
        btn_layout.addWidget(self.stop_monitor_btn)
        main_layout.addLayout(btn_layout)

        # Placeholder for webhook management and logs
        main_layout.addWidget(QLabel('Webhooks and Logs (coming soon)'))

        # Log viewer (hidden by default)
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.hide()
        main_layout.addWidget(self.log_viewer)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage('Ready')

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu('View')
        toggle_log_action = QAction('Show Log Viewer', self, checkable=True)
        toggle_log_action.setChecked(False)
        toggle_log_action.triggered.connect(self.toggle_log_viewer)
        view_menu.addAction(toggle_log_action)

        # System tray integration (placeholder)
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        tray_menu = QMenu()
        show_action = QAction('Show', self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        quit_action = QAction('Quit', self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Connect buttons to dialogs
        self.add_project_btn.clicked.connect(self.open_add_project_dialog)
        self.edit_project_btn.clicked.connect(self.open_edit_project_dialog)
        self.remove_project_btn.clicked.connect(self.remove_selected_project)
        self.start_monitor_btn.clicked.connect(self.start_monitoring)
        self.stop_monitor_btn.clicked.connect(self.stop_monitoring)
        self.project_list.itemDoubleClicked.connect(self.open_edit_project_dialog)

        self.monitor_thread = None
        self.settings = self.load_settings()
        self.schedule_timer = threading.Thread(target=self.schedule_checker, daemon=True)
        self.schedule_timer_stop = threading.Event()
        self.schedule_timer.start()

        self.refresh_project_list()

    def open_add_project_dialog(self):
        dialog = ProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.projects.append(data)
            self.save_config()
            self.refresh_project_list()
            self.append_log(f"Project '{data['name']}' added with {len(data['webhooks'])} webhook(s).")
            self.status_bar.showMessage(f"Project '{data['name']}' added.", 3000)

    def open_edit_project_dialog(self, item=None):
        from PyQt5.QtWidgets import QListWidgetItem
        if isinstance(item, QListWidgetItem):
            row = self.project_list.row(item)
        else:
            row = self.project_list.currentRow()
        if row >= 0:
            project = self.projects[row]
            dialog = ProjectDialog(self, project=project)
            if dialog.exec_() == QDialog.Accepted:
                self.projects[row] = dialog.get_data()
                self.save_config()
                self.refresh_project_list()
                self.append_log(f"Project '{project['name']}' updated.")
                self.status_bar.showMessage(f"Project '{project['name']}' updated.", 3000)
        else:
            QMessageBox.warning(self, 'Edit Project', 'Please select a project to edit.')

    def remove_selected_project(self):
        row = self.project_list.currentRow()
        if row >= 0:
            removed = self.projects.pop(row)
            self.save_config()
            self.refresh_project_list()
            self.append_log(f"Project '{removed['name']}' removed.")
            self.status_bar.showMessage(f"Project '{removed['name']}' removed.", 3000)
        else:
            QMessageBox.warning(self, 'No Selection', 'Please select a project to remove.')

    def refresh_project_list(self):
        self.project_list.clear()
        for proj in self.projects:
            wh_count = len(proj.get('webhooks', []))
            self.project_list.addItem(f"{proj['name']} ({wh_count} webhook{'s' if wh_count != 1 else ''})")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'projects': self.projects}, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', f'Failed to save config: {e}')
            self.append_log(f"Error saving config: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.projects = data.get('projects', [])
            except Exception as e:
                QMessageBox.critical(self, 'Load Error', f'Failed to load config: {e}')
                self.append_log(f"Error loading config: {e}")

    def append_log(self, message):
        self.log_viewer.append(message)

    def toggle_log_viewer(self, checked):
        self.log_viewer.setVisible(checked)

    def start_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            QMessageBox.warning(self, 'Monitoring', 'Monitoring is already running.')
            return
        self.monitor_thread = MonitorWorker(self.projects)
        self.monitor_thread.log_signal.connect(self.append_log)
        self.monitor_thread.status_signal.connect(self.status_bar.showMessage)
        self.monitor_thread.start()
        self.start_monitor_btn.setEnabled(False)
        self.stop_monitor_btn.setEnabled(True)
        self.status_bar.showMessage('Monitoring started.', 3000)
        self.append_log('Monitoring started.')

    def stop_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread.wait()
            self.append_log('Monitoring stopped.')
            self.status_bar.showMessage('Monitoring stopped.', 3000)
        self.start_monitor_btn.setEnabled(True)
        self.stop_monitor_btn.setEnabled(False)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self, settings=self.settings)
        if dialog.exec_() == QDialog.Accepted:
            self.settings = dialog.get_settings()
            self.save_settings()
            self.apply_startup_setting()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('settings', {'start_with_windows': False, 'schedules': []})
            except Exception:
                return {'start_with_windows': False, 'schedules': []}
        return {'start_with_windows': False, 'schedules': []}

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['settings'] = self.settings
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def apply_startup_setting(self):
        if platform.system() == 'Windows':
            startup_dir = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            shortcut_path = os.path.join(startup_dir, 'UE4GitReporterDesktop.lnk')
            if self.settings.get('start_with_windows'):
                # Create shortcut if not exists
                import winshell
                from win32com.client import Dispatch
                target = sys.executable
                script = os.path.abspath(__file__)
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = target
                shortcut.Arguments = f'"{script}"'
                shortcut.WorkingDirectory = os.path.dirname(script)
                shortcut.save()
            else:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)

    def schedule_checker(self):
        while not self.schedule_timer_stop.is_set():
            now = datetime.datetime.now()
            for sched in self.settings.get('schedules', []):
                if now.strftime('%H:%M') == sched['time'] and now.weekday() in sched['days']:
                    if not (self.monitor_thread and self.monitor_thread.isRunning()):
                        self.start_monitoring()
            time.sleep(30)

    def closeEvent(self, event):
        # Ensure monitoring and schedule checker are stopped before closing
        self.schedule_timer_stop.set()
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread.wait()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 