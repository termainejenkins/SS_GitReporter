import sys
import os
import json
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMenuBar, QAction, QSystemTrayIcon, QStyle, QMenu,
    QDialog, QLineEdit, QComboBox, QFormLayout, QMessageBox, QListWidgetItem, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Webhook')
        self.setModal(True)
        layout = QFormLayout(self)

        self.webhook_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(MESSAGE_FORMATS)

        layout.addRow('Discord Webhook:', self.webhook_edit)
        layout.addRow('Message Format:', self.format_combo)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton('OK')
        self.cancel_btn = QPushButton('Cancel')
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_data(self):
        return {
            'webhook': self.webhook_edit.text(),
            'format': self.format_combo.currentText()
        }

class ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Project')
        self.setModal(True)
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.path_edit = QLineEdit()
        form_layout.addRow('Project Name:', self.name_edit)
        form_layout.addRow('Project Path:', self.path_edit)
        layout.addLayout(form_layout)

        # Webhook management
        self.webhook_list = QListWidget()
        layout.addWidget(QLabel('Webhooks'))
        layout.addWidget(self.webhook_list)
        webhook_btn_layout = QHBoxLayout()
        self.add_webhook_btn = QPushButton('Add Webhook')
        self.remove_webhook_btn = QPushButton('Remove Webhook')
        webhook_btn_layout.addWidget(self.add_webhook_btn)
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
        self.remove_webhook_btn.clicked.connect(self.remove_selected_webhook)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def open_add_webhook_dialog(self):
        dialog = WebhookDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.webhooks.append(data)
            self.refresh_webhook_list()

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
        self.remove_project_btn = QPushButton('Remove Project')
        self.start_monitor_btn = QPushButton('Start Monitoring')
        self.stop_monitor_btn = QPushButton('Stop Monitoring')
        self.stop_monitor_btn.setEnabled(False)
        btn_layout.addWidget(self.add_project_btn)
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
        self.remove_project_btn.clicked.connect(self.remove_selected_project)
        self.start_monitor_btn.clicked.connect(self.start_monitoring)
        self.stop_monitor_btn.clicked.connect(self.stop_monitoring)

        self.monitor_thread = None

        self.refresh_project_list()

        # TODO: Add webhook management UI
        # TODO: Implement message formatting logic

    def open_add_project_dialog(self):
        dialog = ProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.projects.append(data)
            self.save_config()
            self.refresh_project_list()
            self.append_log(f"Project '{data['name']}' added with {len(data['webhooks'])} webhook(s).")
            self.status_bar.showMessage(f"Project '{data['name']}' added.", 3000)

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 