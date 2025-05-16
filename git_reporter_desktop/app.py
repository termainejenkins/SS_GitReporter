import sys
import os
import json
import time
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMenuBar, QAction, QSystemTrayIcon, QStyle, QMenu,
    QDialog, QLineEdit, QComboBox, QFormLayout, QMessageBox, QListWidgetItem, QTextEdit, QFileDialog,
    QTimeEdit, QCheckBox, QDialogButtonBox, QSpinBox, QGroupBox, QGridLayout, QTabWidget, QProgressDialog, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QIcon
import shutil
import platform
import threading
import datetime
import subprocess
import re
from git_reporter.config_utils import (
    atomic_save_json, backup_config, load_config_with_recovery, CURRENT_CONFIG_VERSION, config_lock
)
import traceback

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
    'Daily summary',
    'AI Summary'
]

WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

def get_no_window_startupinfo():
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None

def get_config_path():
    if sys.platform == 'win32':
        base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base_dir = os.path.expanduser('~')
    config_dir = os.path.join(base_dir, 'GitReporter')
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, 'desktop_config.json')

DEFAULT_CONFIG = {
    "version": CURRENT_CONFIG_VERSION,
    "projects": [],
    "settings": {
        "start_with_windows": False,
        "schedules": [],
        "master_frequency": 1,
        "auto_start_monitoring": True,
        "always_on_top": False,
        "dark_mode": False,
        "start_with_log_open": False,
        "show_inline_progress_bars": True
    }
}

CONFIG_FILE = get_config_path()
LOG_FILE = os.path.join(os.path.dirname(CONFIG_FILE), 'app.log')

# Set up file logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logging.info(f"App started. Config file: {CONFIG_FILE}")

# At startup, log PATH and check for git
logging.info(f"PATH: {os.environ.get('PATH')}")
git_path = shutil.which('git')
if git_path:
    logging.info(f"git found at: {git_path}")
else:
    logging.error("git not found on PATH! Git operations will fail.")

# Unified load/save for both projects and settings
def load_all():
    logging.info(f"Loading config from {CONFIG_FILE}")
    with config_lock:
        data = load_config_with_recovery(CONFIG_FILE, DEFAULT_CONFIG)
    logging.info("Config loaded successfully.")
    return data.get('projects', []), data.get('settings', {})

def save_all(projects, settings):
    with config_lock:
        backup_config(CONFIG_FILE)
        data = {
            'version': CURRENT_CONFIG_VERSION,
            'projects': projects,
            'settings': settings
        }
        atomic_save_json(CONFIG_FILE, data)
    logging.info(f"Config saved to {CONFIG_FILE}")

MONITOR_INTERVAL_SECONDS = 60  # Default check interval (can be made configurable)

def run_git_command(args, cwd):
    try:
        logging.info(f"Running git command: {' '.join(args)} in {cwd}")
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo())
        logging.info(f"Git command output: {result.stdout.strip()}")
        return result.stdout.strip()
    except FileNotFoundError as e:
        logging.error(f"Git not found: {e}")
        return None
    except Exception as e:
        logging.error(f"Git command failed: {e}")
        return None

class MonitorWorker(QThread):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, projects, monitor_interval=60):
        super().__init__()
        self.projects = projects
        self.running = False
        self.last_commit_hashes = {}  # Track last commit per project/branch
        self.last_sent_times = {}     # Track last sent time per webhook
        self.monitor_interval = monitor_interval

    def run(self):
        self.running = True
        self.log_signal.emit('Background monitoring started.')
        logging.info('Background monitoring started.')
        while self.running:
            now = time.time()
            for project in self.projects:
                name = project.get('name', 'Unknown')
                path = project.get('path', '')
                branches = project.get('branches', []) or ['']
                filters = project.get('filters', {})
                webhooks = project.get('webhooks', [])
                if not os.path.exists(path):
                    msg = f"[ERROR] Project path does not exist: {path}"
                    self.log_signal.emit(msg)
                    logging.error(msg)
                    continue
                for branch in branches:
                    try:
                        if branch:
                            run_git_command(['git', 'checkout', branch], cwd=path)
                        monitor = GitMonitor(path, ignored_files=[])
                    except Exception as e:
                        msg = f"[ERROR] Could not initialize GitMonitor for '{name}' branch '{branch}': {e}"
                        self.log_signal.emit(msg)
                        logging.error(msg)
                        continue
                    latest_commit = run_git_command(['git', 'rev-parse', 'HEAD'], cwd=path)
                    branch_key = f"{path}|{branch}"
                    if not latest_commit:
                        msg = f"[ERROR] Could not get latest commit for '{name}' [{branch}]"
                        self.log_signal.emit(msg)
                        logging.error(msg)
                        continue
                    last_hash = self.last_commit_hashes.get(branch_key)
                    if last_hash == latest_commit:
                        msg = f"No new commits for '{name}' [{branch}]."
                        self.log_signal.emit(msg)
                        logging.info(msg)
                        continue
                    self.last_commit_hashes[branch_key] = latest_commit
                    status, commits = monitor.get_changes()
                    send = False
                    filtered_commits = ''
                    filtered_status = ''
                    if filters.get('commits', True) and commits:
                        filtered_commits = commits
                        send = True
                    if filters.get('merges', False) and commits:
                        if any('merge' in line.lower() for line in commits.split('\n')):
                            filtered_commits = '\n'.join([line for line in commits.split('\n') if 'merge' in line.lower()])
                            send = True
                    if filters.get('tags', False):
                        tags = run_git_command(['git', 'tag', '--contains', latest_commit], cwd=path)
                        if tags:
                            filtered_commits += f"\nTags: {tags}"
                            send = True
                    if filters.get('filetypes', '') and status:
                        types = [ft.strip() for ft in filters['filetypes'].split(',') if ft.strip()]
                        filtered_lines = [line for line in status.split('\n') if any(line.endswith(t) for t in types)]
                        if filtered_lines:
                            filtered_status = '\n'.join(filtered_lines)
                            send = True
                    if not send:
                        msg = f"No matching changes for '{name}' [{branch}]."
                        self.log_signal.emit(msg)
                        logging.info(msg)
                        continue
                    for wh in webhooks:
                        wh_id = f"{path}|{branch}|{wh['webhook']}"
                        freq = int(wh.get('frequency', 60))
                        last_sent = self.last_sent_times.get(wh_id, 0)
                        if now - last_sent < freq * 60:
                            msg = f"Skipping webhook {wh['webhook']} for '{name}' [{branch}] (frequency not elapsed)"
                            self.log_signal.emit(msg)
                            logging.info(msg)
                            continue
                        template = wh.get('template', '')
                        msg = self.format_message(wh['format'], f"{name} [{branch}]", filtered_status or status, filtered_commits or commits, branch, template, path)
                        logmsg = f"Sending {wh['format']} report to {wh['webhook']} for '{name}' [{branch}]..."
                        self.log_signal.emit(logmsg)
                        logging.info(logmsg)
                        try:
                            client = DiscordClient(wh['webhook'])
                            ok = False
                            try:
                                ok = client.send_message(msg)
                            except Exception as e:
                                logging.error(f"DiscordClient.send_message error: {e}")
                            if ok:
                                okmsg = f"[OK] Report sent to {wh['webhook']} for '{name}' [{branch}]."
                                self.log_signal.emit(okmsg)
                                logging.info(okmsg)
                                self.last_sent_times[wh_id] = now
                            else:
                                errmsg = f"[ERROR] Failed to send report to {wh['webhook']} for '{name}' [{branch}]."
                                self.log_signal.emit(errmsg)
                                logging.error(errmsg)
                        except Exception as e:
                            errmsg = f"[ERROR] Exception sending to Discord: {e}"
                            self.log_signal.emit(errmsg)
                            logging.error(errmsg)
            self.status_signal.emit('Monitoring cycle complete.')
            logging.info('Monitoring cycle complete.')
            for _ in range(self.monitor_interval):
                if not self.running:
                    break
                time.sleep(1)
        self.log_signal.emit('Background monitoring stopped.')
        self.status_signal.emit('Monitoring stopped.')
        logging.info('Background monitoring stopped.')
        logging.info('Monitoring stopped.')

    def stop(self):
        self.running = False

    @staticmethod
    def format_message(fmt, project_name, status, commits, branch='', template=None, repo_path=None):
        if fmt == 'AI Summary':
            import subprocess, os, re
            summary = ''
            emoji_map = {
                'fix': '🐛', 'bug': '🐛',
                'feature': '✨', 'add': '✨',
                'docs': '📝', 'doc': '📝',
                'refactor': '♻️',
                'breaking change': '⚠️',
                'delete': '🔥', 'remove': '🔥',
                'build': '🛠️', 'chore': '🛠️',
                'deps': '📦', 'dependency': '📦',
                'test': '🚨', 'ci': '🚨',
            }
            if repo_path and os.path.isdir(os.path.join(repo_path, '.git')):
                try:
                    branch_name = branch or ''
                    if not branch_name:
                        branch_name = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout.strip()
                    log_out = subprocess.run(['git', 'log', '-1', '--pretty=%s||%an'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout.strip()
                    commit_msg, author = log_out.split('||') if '||' in log_out else (log_out, '')
                    status_out = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout
                    diffstat = subprocess.run(['git', 'diff', '--stat'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout
                    added, modified, deleted = [], [], []
                    file_types = {}
                    for line in status_out.splitlines():
                        fname = line[3:].strip() if len(line) > 3 else ''
                        ext = os.path.splitext(fname)[1].lower()
                        if ext:
                            file_types[ext] = file_types.get(ext, 0) + 1
                        if line.startswith('A '):
                            added.append(fname)
                        elif line.startswith('M '):
                            modified.append(fname)
                        elif line.startswith('D '):
                            deleted.append(fname)
                    # Detect keywords and emojis
                    keywords = []
                    emojis = set()
                    for word, emoji in emoji_map.items():
                        if re.search(rf'\b{word}\b', commit_msg, re.IGNORECASE):
                            keywords.append(word)
                            emojis.add(emoji)
                    # Also scan file names for delete/remove/build/test
                    for fname in added + modified + deleted:
                        for word, emoji in emoji_map.items():
                            if word in fname.lower():
                                emojis.add(emoji)
                    # Format summary with emojis
                    summary = f"Branch: {branch_name}\n"
                    summary += f"Latest commit: {commit_msg.strip()} (by {author.strip()})\n"
                    if added:
                        summary += f"{emoji_map.get('add','')} Added: {', '.join(added)}\n"
                    if modified:
                        summary += f"{emoji_map.get('feature','')} Modified: {', '.join(modified)}\n"
                    if deleted:
                        summary += f"{emoji_map.get('delete','')} Deleted: {', '.join(deleted)}\n"
                    if file_types:
                        summary += "File types: " + ', '.join(f"{k} x{v}" for k, v in file_types.items()) + "\n"
                    if diffstat.strip():
                        summary += f"Diffstat:\n{diffstat.strip()}\n"
                    if keywords:
                        summary += f"Keywords: {' '.join([emoji_map.get(k, '') for k in keywords])} ({', '.join(keywords)})\n"
                    if emojis and not keywords:
                        summary += f"Visual cues: {' '.join(emojis)}\n"
                except Exception as e:
                    summary = f"[Summary generation failed: {e}]"
            else:
                summary = '[Summary generation failed: not a git repo]'
            return summary
        # If a custom template is provided, use it
        if template:
            # For demonstration, use simple replacements
            msg = template
            msg = msg.replace('{project}', project_name)
            msg = msg.replace('{branch}', branch)
            msg = msg.replace('{commit_message}', commits or '')
            msg = msg.replace('{files_changed}', status or '')
            # Add more variables as needed
            return msg
        # Otherwise, use the built-in formats
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

def get_git_branches(repo_path):
    try:
        result = subprocess.run(['git', 'branch', '--list'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo())
        branches = [line.strip().lstrip('* ').strip() for line in result.stdout.splitlines() if line.strip()]
        return branches
    except Exception:
        return []

class WebhookTestWorker(QThread):
    result_signal = pyqtSignal(bool, str)
    def __init__(self, url, msg):
        super().__init__()
        self.url = url
        self.msg = msg
    def run(self):
        try:
            client = DiscordClient(self.url)
            ok = client.send_message(self.msg)
            if ok:
                self.result_signal.emit(True, 'Test message sent successfully!')
            else:
                self.result_signal.emit(False, 'Failed to send test message.')
        except Exception as e:
            self.result_signal.emit(False, f'Error: {e}')

class CheckAllNowWorker(QThread):
    log_signal = pyqtSignal(str)
    done_signal = pyqtSignal()
    progress_signal = pyqtSignal(int)
    per_project_progress_signal = pyqtSignal(str, int, int)  # name, current, total
    def __init__(self, projects, fmt):
        super().__init__()
        self.projects = projects
        self.fmt = fmt
        self._should_stop = False
    def stop(self):
        self._should_stop = True
    def run(self):
        try:
            print('[DEBUG] Entered CheckAllNowWorker.run')
            self.log_signal.emit('[DEBUG] Entered CheckAllNowWorker.run')
            import time
            now = time.time()
            total = sum(len((p.get('branches', []) or [''])) for p in self.projects)
            count = 0
            for project in self.projects:
                if self._should_stop:
                    self.log_signal.emit('[DEBUG] Worker stop flag set, exiting run loop.')
                    break
                name = project.get('name', 'Unknown')
                path = project.get('path', '')
                branches = project.get('branches', []) or ['']
                filters = project.get('filters', {})
                webhooks = project.get('webhooks', [])
                if not name or not path or not isinstance(webhooks, list):
                    msg = f"[ERROR] Invalid project data: {project}"
                    print(msg)
                    self.log_signal.emit(msg)
                    count += len(branches)
                    self.progress_signal.emit(count)
                    self.per_project_progress_signal.emit(name, count, total)
                    continue
                if not os.path.exists(path):
                    msg = f"[ERROR] Project path does not exist: {path}"
                    print(msg)
                    self.log_signal.emit(msg)
                    count += len(branches)
                    self.progress_signal.emit(count)
                    self.per_project_progress_signal.emit(name, count, total)
                    continue
                for branch in branches:
                    if self._should_stop:
                        self.log_signal.emit('[DEBUG] Worker stop flag set, exiting branch loop.')
                        break
                    try:
                        if branch:
                            subprocess.run(['git', 'checkout', branch], cwd=path, capture_output=True, text=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo())
                        monitor = GitMonitor(path, ignored_files=[])
                    except Exception as e:
                        msg = f"[ERROR] Could not initialize GitMonitor for '{name}' branch '{branch}': {e}"
                        print(msg)
                        self.log_signal.emit(msg)
                        count += 1
                        self.progress_signal.emit(count)
                        self.per_project_progress_signal.emit(name, count, total)
                        continue
                    latest_commit = monitor._run_git_command(['git', 'rev-parse', 'HEAD'])
                    if not latest_commit:
                        msg = f"[ERROR] Could not get latest commit for '{name}' [{branch}]"
                        print(msg)
                        self.log_signal.emit(msg)
                        count += 1
                        self.progress_signal.emit(count)
                        self.per_project_progress_signal.emit(name, count, total)
                        continue
                    status, commits = monitor.get_changes()
                    send = False
                    filtered_commits = ''
                    filtered_status = ''
                    if filters.get('commits', True) and commits:
                        filtered_commits = commits
                        send = True
                    if filters.get('merges', False) and commits:
                        if any('merge' in line.lower() for line in commits.split('\n')):
                            filtered_commits = '\n'.join([line for line in commits.split('\n') if 'merge' in line.lower()])
                            send = True
                    if filters.get('tags', False):
                        tags = monitor._run_git_command(['git', 'tag', '--contains', latest_commit])
                        if tags:
                            filtered_commits += f"\nTags: {tags}"
                            send = True
                    if filters.get('filetypes', '') and status:
                        types = [ft.strip() for ft in filters['filetypes'].split(',') if ft.strip()]
                        filtered_lines = [line for line in status.split('\n') if any(line.endswith(t) for t in types)]
                        if filtered_lines:
                            filtered_status = '\n'.join(filtered_lines)
                            send = True
                    if not send:
                        msg = f"No matching changes for '{name}' [{branch}]."
                        print(msg)
                        self.log_signal.emit(msg)
                        count += 1
                        self.progress_signal.emit(count)
                        self.per_project_progress_signal.emit(name, count, total)
                        continue
                    for wh in webhooks:
                        if self._should_stop:
                            self.log_signal.emit('[DEBUG] Worker stop flag set, exiting webhook loop.')
                            break
                        msg = f"[Check Now] Sending {self.fmt} report to {wh.get('webhook','')} for '{name}' [{branch}]..."
                        print(msg)
                        self.log_signal.emit(msg)
                        try:
                            client = DiscordClient(wh.get('webhook',''))
                            if client.send_message(MonitorWorker.format_message(self.fmt, f"{name} [{branch}]", filtered_status or status, filtered_commits or commits, branch, wh.get('template', ''), path)):
                                okmsg = f"[OK] Report sent to {wh.get('webhook','')} for '{name}' [{branch}]."
                                print(okmsg)
                                self.log_signal.emit(okmsg)
                            else:
                                errmsg = f"[ERROR] Failed to send report to {wh.get('webhook','')} for '{name}' [{branch}]."
                                print(errmsg)
                                self.log_signal.emit(errmsg)
                        except Exception as e:
                            errmsg = f"[ERROR] Exception sending to Discord: {e}"
                            print(errmsg)
                            self.log_signal.emit(errmsg)
                    count += 1
                    self.progress_signal.emit(count)
                    self.per_project_progress_signal.emit(name, count, total)
            print('[DEBUG] Exiting CheckAllNowWorker.run')
            self.log_signal.emit('[DEBUG] Exiting CheckAllNowWorker.run')
        except Exception as e:
            tb = traceback.format_exc()
            msg = f"[FATAL ERROR] Exception in CheckAllNowWorker: {e}\n{tb}"
            print(msg)
            self.log_signal.emit(msg)
        finally:
            print('[DEBUG] Emitting done_signal from CheckAllNowWorker')
            self.done_signal.emit()

class WebhookDialog(QDialog):
    def __init__(self, parent=None, webhook=None, project_name=None, status=None, commits=None, branch=None):
        super().__init__(parent)
        self.setWindowTitle('Add/Edit Webhook')
        self.setModal(True)
        self.project_name = project_name or 'Project'
        self.status = status or 'No status.'
        self.commits = commits or 'No commits.'
        self.branch = branch or ''

        # Tabs for Basic/Advanced
        tabs = QTabWidget(self)
        basic_tab = QWidget()
        advanced_tab = QWidget()
        tabs.addTab(basic_tab, 'Basic')
        tabs.addTab(advanced_tab, 'Advanced')
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(tabs)

        # Basic tab layout
        layout = QFormLayout(basic_tab)
        self.webhook_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(MESSAGE_FORMATS)
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(5, 1440)
        self.freq_spin.setValue(60)
        self.freq_spin.setSuffix(' min')
        self.test_btn = QPushButton('Test')
        self.preview_btn = QPushButton('Preview')
        layout.addRow('Discord Webhook:', self.webhook_edit)
        layout.addRow('Message Format:', self.format_combo)
        layout.addRow('Frequency (minutes):', self.freq_spin)
        layout.addRow(self.test_btn, self.preview_btn)

        # Advanced tab layout
        adv_layout = QVBoxLayout(advanced_tab)
        adv_layout.addWidget(QLabel('Custom Message Template (optional):'))
        self.template_edit = QTextEdit()
        self.template_edit.setPlaceholderText('Use {commit_message}, {author}, {files_changed}, {branch}, {project}, {summary}...')
        adv_layout.addWidget(self.template_edit)
        adv_layout.addWidget(QLabel('Leave blank to use the selected format.'))
        self.summary_btn = QPushButton('Generate Summary')
        adv_layout.addWidget(self.summary_btn)
        self.summary_btn.clicked.connect(self.generate_summary)

        self.ok_btn = QPushButton('OK')
        self.cancel_btn = QPushButton('Cancel')
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.test_btn.clicked.connect(self.threaded_test_webhook)
        self.preview_btn.clicked.connect(self.preview_message)

        if webhook:
            self.webhook_edit.setText(webhook.get('webhook', ''))
            idx = self.format_combo.findText(webhook.get('format', MESSAGE_FORMATS[0]))
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            self.freq_spin.setValue(int(webhook.get('frequency', 60)))
            self.template_edit.setPlainText(webhook.get('template', ''))

    def get_data(self):
        return {
            'webhook': self.webhook_edit.text(),
            'format': self.format_combo.currentText(),
            'frequency': self.freq_spin.value(),
            'template': self.template_edit.toPlainText().strip()
        }

    def threaded_test_webhook(self):
        url = self.webhook_edit.text().strip()
        fmt = self.format_combo.currentText()
        template = self.template_edit.toPlainText().strip()
        msg = MonitorWorker.format_message(self, fmt, self.project_name, self.status, self.commits, self.branch, template)
        if not url:
            QMessageBox.warning(self, 'Test Webhook', 'Please enter a webhook URL.')
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText('Testing...')
        self.worker = WebhookTestWorker(url, msg)
        def on_result(ok, message):
            self.test_btn.setEnabled(True)
            self.test_btn.setText('Test')
            if ok:
                QMessageBox.information(self, 'Test Webhook', message)
            else:
                QMessageBox.critical(self, 'Test Webhook', message)
        self.worker.result_signal.connect(on_result)
        self.worker.start()

    def preview_message(self):
        fmt = self.format_combo.currentText()
        template = self.template_edit.toPlainText().strip()
        msg = MonitorWorker.format_message(self, fmt, self.project_name, self.status, self.commits, self.branch, template)
        QMessageBox.information(self, 'Preview Message', msg)

    def generate_summary(self):
        import subprocess, os, re
        repo_path = os.path.dirname(self.parent().path_edit.text()) if hasattr(self.parent(), 'path_edit') else os.getcwd()
        emoji_map = {
            'fix': '🐛', 'bug': '🐛',
            'feature': '✨', 'add': '✨',
            'docs': '📝', 'doc': '📝',
            'refactor': '♻️',
            'breaking change': '⚠️',
            'delete': '🔥', 'remove': '🔥',
            'build': '🛠️', 'chore': '🛠️',
            'deps': '📦', 'dependency': '📦',
            'test': '🚨', 'ci': '🚨',
        }
        if not os.path.isdir(os.path.join(repo_path, '.git')):
            QMessageBox.warning(self, 'Generate Summary', 'Not a valid git repository.')
            return
        try:
            branch_name = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout.strip()
            log_out = subprocess.run(['git', 'log', '-1', '--pretty=%s||%an'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout.strip()
            commit_msg, author = log_out.split('||') if '||' in log_out else (log_out, '')
            status_out = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout
            diffstat = subprocess.run(['git', 'diff', '--stat'], cwd=repo_path, capture_output=True, text=True, check=True, creationflags=WIN_NO_WINDOW, startupinfo=get_no_window_startupinfo()).stdout
            added, modified, deleted = [], [], []
            file_types = {}
            for line in status_out.splitlines():
                fname = line[3:].strip() if len(line) > 3 else ''
                ext = os.path.splitext(fname)[1].lower()
                if ext:
                    file_types[ext] = file_types.get(ext, 0) + 1
                if line.startswith('A '):
                    added.append(fname)
                elif line.startswith('M '):
                    modified.append(fname)
                elif line.startswith('D '):
                    deleted.append(fname)
            keywords = []
            emojis = set()
            for word, emoji in emoji_map.items():
                if re.search(rf'\b{word}\b', commit_msg, re.IGNORECASE):
                    keywords.append(word)
                    emojis.add(emoji)
            for fname in added + modified + deleted:
                for word, emoji in emoji_map.items():
                    if word in fname.lower():
                        emojis.add(emoji)
            summary = f"Branch: {branch_name}\n"
            summary += f"Latest commit: {commit_msg.strip()} (by {author.strip()})\n"
            if added:
                summary += f"{emoji_map.get('add','')} Added: {', '.join(added)}\n"
            if modified:
                summary += f"{emoji_map.get('feature','')} Modified: {', '.join(modified)}\n"
            if deleted:
                summary += f"{emoji_map.get('delete','')} Deleted: {', '.join(deleted)}\n"
            if file_types:
                summary += "File types: " + ', '.join(f"{k} x{v}" for k, v in file_types.items()) + "\n"
            if diffstat.strip():
                summary += f"Diffstat:\n{diffstat.strip()}\n"
            if keywords:
                summary += f"Keywords: {' '.join([emoji_map.get(k, '') for k in keywords])} ({', '.join(keywords)})\n"
            if emojis and not keywords:
                summary += f"Visual cues: {' '.join(emojis)}\n"
        except Exception as e:
            summary = f"[Summary generation failed: {e}]"
        cursor = self.template_edit.textCursor()
        template = self.template_edit.toPlainText()
        if '{summary}' in template:
            template = template.replace('{summary}', summary)
            self.template_edit.setPlainText(template)
        else:
            cursor.insertText(summary)

class ProjectListItemWidget(QWidget):
    def __init__(self, name, wh_count, status_emoji='', tooltip='', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.label = QLabel(f"{status_emoji} {name} ({wh_count} webhook{'s' if wh_count != 1 else ''})")
        layout.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(12)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        layout.setContentsMargins(0, 0, 0, 0)
        if tooltip:
            self.setToolTip(tooltip)
        self.setLayout(layout)

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

        # Branch selection
        self.branch_group = QGroupBox('Branches to Monitor')
        branch_layout = QVBoxLayout()
        self.branch_checks = []
        self.branch_group.setLayout(branch_layout)
        layout.addWidget(self.branch_group)
        self.path_edit.textChanged.connect(self.update_branches)
        self.update_branches()  # Populate if editing

        # Change type filtering
        self.filter_group = QGroupBox('Change Type Filters')
        filter_layout = QGridLayout()
        self.commit_cb = QCheckBox('Commits')
        self.merge_cb = QCheckBox('Merges')
        self.tag_cb = QCheckBox('Tags')
        self.filetype_edit = QLineEdit()
        self.filetype_edit.setPlaceholderText('e.g. .cpp,.uasset')
        filter_layout.addWidget(self.commit_cb, 0, 0)
        filter_layout.addWidget(self.merge_cb, 0, 1)
        filter_layout.addWidget(self.tag_cb, 0, 2)
        filter_layout.addWidget(QLabel('File Types:'), 1, 0)
        filter_layout.addWidget(self.filetype_edit, 1, 1, 1, 2)
        self.filter_group.setLayout(filter_layout)
        layout.addWidget(self.filter_group)

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
            # Restore branch and filter settings
            self.selected_branches = set(project.get('branches', []))
            self.update_branches()
            filters = project.get('filters', {})
            self.commit_cb.setChecked(filters.get('commits', True))
            self.merge_cb.setChecked(filters.get('merges', False))
            self.tag_cb.setChecked(filters.get('tags', False))
            self.filetype_edit.setText(filters.get('filetypes', ''))
        else:
            self.selected_branches = set()
            self.update_branches()
            self.commit_cb.setChecked(True)

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

    def update_branches(self):
        repo_path = self.path_edit.text().strip()
        branches = get_git_branches(repo_path) if os.path.isdir(os.path.join(repo_path, '.git')) else []
        # Remove old checkboxes
        for cb in self.branch_checks:
            self.branch_group.layout().removeWidget(cb)
            cb.deleteLater()
        self.branch_checks = []
        for branch in branches:
            cb = QCheckBox(branch)
            if branch in getattr(self, 'selected_branches', set()):
                cb.setChecked(True)
            self.branch_group.layout().addWidget(cb)
            self.branch_checks.append(cb)

    def get_selected_branches(self):
        return [cb.text() for cb in self.branch_checks if cb.isChecked()]

    def get_filters(self):
        return {
            'commits': self.commit_cb.isChecked(),
            'merges': self.merge_cb.isChecked(),
            'tags': self.tag_cb.isChecked(),
            'filetypes': self.filetype_edit.text().strip()
        }

    def get_data(self):
        return {
            'name': self.name_edit.text(),
            'path': self.path_edit.text(),
            'branches': self.get_selected_branches(),
            'filters': self.get_filters(),
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

        # Auto Start Monitoring
        self.auto_start_monitoring_cb = QCheckBox('Auto Start Monitoring')
        layout.addWidget(self.auto_start_monitoring_cb)

        # Start With Log Open
        self.start_with_log_open_cb = QCheckBox('Start With Log Open')
        layout.addWidget(self.start_with_log_open_cb)

        # Show Inline Progress Bars
        self.show_inline_progress_cb = QCheckBox('Show Inline Progress Bars')
        layout.addWidget(self.show_inline_progress_cb)

        # Master monitoring frequency
        freq_layout = QHBoxLayout()
        freq_label = QLabel('Master Monitoring Frequency (minutes):')
        self.master_freq_spin = QSpinBox()
        self.master_freq_spin.setRange(1, 120)
        self.master_freq_spin.setValue(1)
        self.master_freq_spin.setSuffix(' min')
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.master_freq_spin)
        layout.addLayout(freq_layout)

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
            self.master_freq_spin.setValue(settings.get('master_frequency', 1))
            self.auto_start_monitoring_cb.setChecked(settings.get('auto_start_monitoring', True))
            self.start_with_log_open_cb.setChecked(settings.get('start_with_log_open', False))
            self.show_inline_progress_cb.setChecked(settings.get('show_inline_progress_bars', True))
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
            'schedules': self.schedules,
            'master_frequency': self.master_freq_spin.value(),
            'auto_start_monitoring': self.auto_start_monitoring_cb.isChecked(),
            'start_with_log_open': self.start_with_log_open_cb.isChecked(),
            'show_inline_progress_bars': self.show_inline_progress_cb.isChecked()
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

class TestAllStatusWorker(QThread):
    status_signal = pyqtSignal(dict)
    done_signal = pyqtSignal()
    progress_signal = pyqtSignal(int)
    per_project_progress_signal = pyqtSignal(str, int, int)  # name, current, total
    def __init__(self, projects):
        super().__init__()
        self.projects = projects
    def run(self):
        from PyQt5.QtWidgets import QListWidgetItem
        project_statuses = {}
        total = len(self.projects)
        for idx, project in enumerate(self.projects):
            name = project.get('name', 'Unknown')
            path = project.get('path', '')
            webhooks = project.get('webhooks', [])
            status = {'repo': False, 'webhooks': [], 'details': []}
            if os.path.isdir(path) and os.path.isdir(os.path.join(path, '.git')):
                status['repo'] = True
            else:
                status['details'].append('Missing or invalid git repo')
            for wh in webhooks:
                url = wh.get('webhook', '')
                try:
                    client = DiscordClient(url)
                    ok = client.send_message(f"[Test] Webhook test from UE4 Git Reporter Desktop for project '{name}'")
                    status['webhooks'].append(ok)
                    if not ok:
                        status['details'].append(f"Webhook failed: {url}")
                except Exception as e:
                    status['webhooks'].append(False)
                    status['details'].append(f"Webhook error: {url} ({e})")
            project_statuses[name] = status
            self.status_signal.emit(project_statuses)
            self.progress_signal.emit(idx + 1)
            self.per_project_progress_signal.emit(name, idx + 1, total)
        self.status_signal.emit(project_statuses)
        self.done_signal.emit()

class TestSelectedProjectWorker(QThread):
    status_signal = pyqtSignal(str, dict)
    done_signal = pyqtSignal()
    per_project_progress_signal = pyqtSignal(str, int, int)  # name, current, total
    def __init__(self, project):
        super().__init__()
        self.project = project
    def run(self):
        name = self.project.get('name', 'Unknown')
        path = self.project.get('path', '')
        webhooks = self.project.get('webhooks', [])
        status = {'repo': False, 'webhooks': [], 'details': []}
        total = 1
        if os.path.isdir(path) and os.path.isdir(os.path.join(path, '.git')):
            status['repo'] = True
        else:
            status['details'].append('Missing or invalid git repo')
        for wh in webhooks:
            url = wh.get('webhook', '')
            try:
                client = DiscordClient(url)
                ok = client.send_message(f"[Test] Webhook test from UE4 Git Reporter Desktop for project '{name}'")
                status['webhooks'].append(ok)
                if not ok:
                    status['details'].append(f"Webhook failed: {url}")
            except Exception as e:
                status['webhooks'].append(False)
                status['details'].append(f"Webhook error: {url} ({e})")
        self.status_signal.emit(name, status)
        self.per_project_progress_signal.emit(name, 1, total)
        self.done_signal.emit()

class ImportDataWorker(QThread):
    result_signal = pyqtSignal(list, str)
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            new_projects = data.get('projects', [])
            if not new_projects:
                self.result_signal.emit([], 'No projects found in the selected file.')
            else:
                self.result_signal.emit(new_projects, 'Import successful!')
        except Exception as e:
            self.result_signal.emit([], f'Import failed: {e}')

class ExportDataWorker(QThread):
    result_signal = pyqtSignal(bool, str)
    def __init__(self, path, projects):
        super().__init__()
        self.path = path
        self.projects = projects
    def run(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump({'projects': self.projects}, f, indent=2)
            self.result_signal.emit(True, 'Export successful!')
        except Exception as e:
            self.result_signal.emit(False, f'Export failed: {e}')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        print(f"[DEBUG] MainWindow __init__ called, id: {id(self)}")
        print(f"[DEBUG] MainWindow instance created: {id(self)}")
        self.monitor_status_label = QLabel()
        self.status_bar = self.statusBar()
        self.status_bar.addPermanentWidget(self.monitor_status_label)
        self.update_monitor_status(False)
        self.projects_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.check_worker = None
        with self.projects_lock, self.settings_lock:
            self.projects, self.settings = load_all()
        self.setWindowTitle('UE4 Git Reporter Desktop')
        self.setGeometry(100, 100, 800, 500)
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)))

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Project list and controls
        test_all_layout = QHBoxLayout()
        self.test_all_btn = QPushButton('Test All')
        test_all_layout.addWidget(QLabel('Projects'))
        test_all_layout.addWidget(self.test_all_btn)
        main_layout.addLayout(test_all_layout)
        self.project_list = QListWidget()
        main_layout.addWidget(self.project_list)
        self.project_list.itemClicked.connect(self.project_item_clicked)
        self.project_test_btn = QPushButton('Test Selected')
        main_layout.addWidget(self.project_test_btn)
        self.project_test_btn.clicked.connect(self.test_selected_project)

        # Master frequency control on the main window
        freq_layout = QHBoxLayout()
        freq_label = QLabel('Master Monitoring Frequency (minutes):')
        self.master_freq_spin = QSpinBox()
        self.master_freq_spin.setRange(1, 120)
        self.master_freq_spin.setValue(self.settings.get('master_frequency', 1))
        self.master_freq_spin.setSuffix(' min')
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.master_freq_spin)
        main_layout.addLayout(freq_layout)
        self.master_freq_spin.valueChanged.connect(self.update_master_frequency)

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

        # Check All Now controls
        check_layout = QHBoxLayout()
        self.check_format_combo = QComboBox()
        self.check_format_combo.addItems(MESSAGE_FORMATS)
        self.check_now_btn = QPushButton('Check All Now')
        self.check_now_cancel_btn = QPushButton('Cancel')
        self.check_now_cancel_btn.setEnabled(False)
        self.check_now_cancel_btn.setVisible(False)
        check_layout.addWidget(QLabel('Format:'))
        check_layout.addWidget(self.check_format_combo)
        check_layout.addWidget(self.check_now_btn)
        check_layout.addWidget(self.check_now_cancel_btn)
        main_layout.addLayout(check_layout)
        # --- SIGNAL RECEIVER DEBUG ---
        try:
            self.check_now_btn.clicked.disconnect()
        except Exception as e:
            print(f"[DEBUG] (init) disconnect failed (may be normal if no previous connection): {e}")
        print(f"[DEBUG] (init) check_now_btn signal receivers before connect: {self.check_now_btn.receivers(self.check_now_btn.clicked)}")
        self.check_now_btn.clicked.connect(self.check_all_now)
        print(f"[DEBUG] (init) check_now_btn signal receivers after connect: {self.check_now_btn.receivers(self.check_now_btn.clicked)}")
        self.check_now_cancel_btn.clicked.connect(self.cancel_check_all_now)

        # Placeholder for webhook management and logs
        main_layout.addWidget(QLabel('Webhooks and Logs (coming soon)'))

        # Log viewer (hidden by default)
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.hide()
        main_layout.addWidget(self.log_viewer)

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

        # Add Options menu
        options_menu = menubar.addMenu('Options')
        settings_action = QAction('Settings', self)
        settings_action.triggered.connect(self.open_settings_dialog)
        options_menu.addAction(settings_action)
        export_action = QAction('Export Data', self)
        export_action.triggered.connect(self.export_data)
        options_menu.addAction(export_action)
        import_action = QAction('Import Data', self)
        import_action.triggered.connect(self.import_data)
        options_menu.addAction(import_action)
        self.always_on_top_action = QAction('Always on Top', self, checkable=True)
        self.always_on_top_action.setChecked(self.settings.get('always_on_top', False))
        self.always_on_top_action.toggled.connect(self.set_always_on_top)
        options_menu.addAction(self.always_on_top_action)
        self.dark_mode_action = QAction('Dark Mode', self, checkable=True)
        self.dark_mode_action.setChecked(self.settings.get('dark_mode', False))
        self.dark_mode_action.toggled.connect(self.set_dark_mode)
        options_menu.addAction(self.dark_mode_action)
        self.set_always_on_top(self.always_on_top_action.isChecked())
        self.set_dark_mode(self.dark_mode_action.isChecked())

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
        self.test_all_btn.clicked.connect(self.test_all_status)
        self.check_now_btn.clicked.connect(self.check_all_now)

        self.monitor_thread = None
        self.monitor_lock = threading.Lock()
        self.monitor_interval = self.settings.get('master_frequency', 1) * 60
        self.schedule_timer = threading.Thread(target=self.schedule_checker, daemon=True)
        self.schedule_timer_stop = threading.Event()
        self.schedule_timer.start()

        self.project_item_widgets = {}  # key: project name, value: ProjectListItemWidget
        self.refresh_project_list()

        # Show log viewer if requested
        if self.settings.get('start_with_log_open', False):
            self.log_viewer.show()
        # Auto start monitoring if requested
        if self.settings.get('auto_start_monitoring', True):
            self.start_monitoring()

        self.check_now_btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        if hasattr(self, 'check_now_btn') and obj == self.check_now_btn:
            print(f"[DEBUG] eventFilter: event type {event.type()} for check_now_btn")
        return super().eventFilter(obj, event)

    def refresh_project_list(self):
        self.project_list.clear()
        self.project_item_widgets = {}
        with self.projects_lock:
            projects_copy = list(self.projects)
        for idx, proj in enumerate(projects_copy):
            wh_count = len(proj.get('webhooks', []))
            name = proj.get('name', 'Unknown')
            status_emoji = ''
            tooltip = ''
            if hasattr(self, 'project_statuses') and name in self.project_statuses:
                status = self.project_statuses[name]
                if not status['repo']:
                    status_emoji = '🔴'
                elif all(status['webhooks']):
                    status_emoji = '🟢'
                elif any(status['webhooks']):
                    status_emoji = '🟡'
                else:
                    status_emoji = '🔴'
                tooltip = '\n'.join(status['details']) if status['details'] else 'All OK'
            widget = ProjectListItemWidget(name, wh_count, status_emoji, tooltip)
            item = QListWidgetItem(self.project_list)
            item.setSizeHint(widget.sizeHint())
            self.project_list.addItem(item)
            self.project_list.setItemWidget(item, widget)
            self.project_item_widgets[name] = widget

    def open_add_project_dialog(self):
        dialog = ProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            with self.projects_lock:
                self.projects.append(data)
            self.save_all()
            self.refresh_project_list()
            self.append_log(f"Project '{data['name']}' added with {len(data['webhooks'])} webhook(s).")
            self.status_bar.showMessage(f"Project '{data['name']}' added.", 3000)

    def open_edit_project_dialog(self, item=None):
        from PyQt5.QtWidgets import QListWidgetItem
        if isinstance(item, QListWidgetItem):
            row = self.project_list.row(item)
        else:
            row = self.project_list.currentRow()
        with self.projects_lock:
            if row >= 0:
                project = self.projects[row]
            else:
                project = None
        if project:
            dialog = ProjectDialog(self, project=project)
            if dialog.exec_() == QDialog.Accepted:
                with self.projects_lock:
                    self.projects[row] = dialog.get_data()
                self.save_all()
                self.refresh_project_list()
                self.append_log(f"Project '{project['name']}' updated.")
                self.status_bar.showMessage(f"Project '{project['name']}' updated.", 3000)
        else:
            QMessageBox.warning(self, 'Edit Project', 'Please select a project to edit.')

    def remove_selected_project(self):
        row = self.project_list.currentRow()
        with self.projects_lock:
            if row >= 0:
                removed = self.projects.pop(row)
            else:
                removed = None
        if removed:
            self.save_all()
            self.refresh_project_list()
            self.append_log(f"Project '{removed['name']}' removed.")
            self.status_bar.showMessage(f"Project '{removed['name']}' removed.", 3000)
        else:
            QMessageBox.warning(self, 'No Selection', 'Please select a project to remove.')

    def save_all(self):
        with self.projects_lock, self.settings_lock:
            save_all(self.projects, self.settings)

    def append_log(self, message):
        self.log_viewer.append(message)
        logging.info(message)

    def toggle_log_viewer(self, checked):
        self.log_viewer.setVisible(checked)

    def start_monitoring(self):
        with self.monitor_lock:
            if self.monitor_thread and self.monitor_thread.isRunning():
                QMessageBox.warning(self, 'Monitoring', 'Monitoring is already running.')
                return
            self.monitor_thread = MonitorWorker(self.projects, monitor_interval=self.monitor_interval)
            self.monitor_thread.log_signal.connect(self.append_log)
            self.monitor_thread.status_signal.connect(self.status_bar.showMessage)
            self.monitor_thread.finished.connect(lambda: self.update_monitor_status(False))
            self.monitor_thread.start()
        self.start_monitor_btn.setEnabled(False)
        self.stop_monitor_btn.setEnabled(True)
        self.status_bar.showMessage('Monitoring started.', 3000)
        self.append_log('Monitoring started.')
        self.update_monitor_status(True)

    def stop_monitoring(self):
        with self.monitor_lock:
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.stop()
                self.monitor_thread.wait()
                self.append_log('Monitoring stopped.')
                self.status_bar.showMessage('Monitoring stopped.', 3000)
            self.start_monitor_btn.setEnabled(True)
            self.stop_monitor_btn.setEnabled(False)
            self.monitor_thread = None
        self.update_monitor_status(False)

    def open_settings_dialog(self):
        with self.settings_lock:
            dialog = SettingsDialog(self, settings=self.settings)
        if dialog.exec_() == QDialog.Accepted:
            with self.settings_lock:
                self.settings = dialog.get_settings()
            self.save_all()
            self.apply_startup_setting()
            with self.settings_lock:
                self.monitor_interval = self.settings.get('master_frequency', 1) * 60

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
                    with self.monitor_lock:
                        if not (self.monitor_thread and self.monitor_thread.isRunning()):
                            self.start_monitoring()
            time.sleep(30)

    def closeEvent(self, event):
        # Ensure monitoring and schedule checker are stopped before closing
        self.schedule_timer_stop.set()
        with self.monitor_lock:
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.stop()
                self.monitor_thread.wait()
            self.monitor_thread = None
        self.update_monitor_status(False)
        # Ensure any running worker thread is stopped and waited for
        if hasattr(self, 'worker') and self.worker is not None:
            try:
                self.worker.stop()
                self.worker.wait()
            except Exception as e:
                print(f'[ERROR] Exception while stopping worker: {e}')
            self.worker = None
        self.save_all()  # Ensure all data is saved before exit
        event.accept()

    def update_master_frequency(self, value):
        with self.settings_lock:
            self.settings['master_frequency'] = value
        self.save_all()
        with self.settings_lock:
            self.monitor_interval = value * 60

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export Projects and Webhooks', '', 'JSON Files (*.json)')
        if path:
            use_inline = self.settings.get('show_inline_progress_bars', True)
            if use_inline:
                self.export_progress.setVisible(True)
                self.export_progress.setRange(0, 0)
                self.export_progress.setValue(0)
            self.export_action.setEnabled(False) if hasattr(self, 'export_action') else None
            self.worker = ExportDataWorker(path, self.projects)
            def on_result(ok, message):
                if use_inline:
                    self.export_progress.setVisible(False)
                if ok:
                    QMessageBox.information(self, 'Export Data', message)
                else:
                    QMessageBox.critical(self, 'Export Data', message)
                if hasattr(self, 'export_action'):
                    self.export_action.setEnabled(True)
            self.worker.result_signal.connect(on_result)
            self.worker.start()

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import Projects and Webhooks', '', 'JSON Files (*.json)')
        if path:
            use_inline = self.settings.get('show_inline_progress_bars', True)
            if use_inline:
                self.import_progress.setVisible(True)
                self.import_progress.setRange(0, 0)
                self.import_progress.setValue(0)
            self.import_action.setEnabled(False) if hasattr(self, 'import_action') else None
            self.worker = ImportDataWorker(path)
            def on_result(new_projects, message):
                if use_inline:
                    self.import_progress.setVisible(False)
                if not new_projects:
                    QMessageBox.warning(self, 'Import Data', message)
                else:
                    choice = QMessageBox.question(self, 'Import Data', 'Do you want to overwrite (Yes) or merge (No) with existing projects?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if choice == QMessageBox.Yes:
                        self.projects = new_projects
                    else:
                        existing_keys = {(p['name'], p['path']) for p in self.projects}
                        for p in new_projects:
                            if (p['name'], p['path']) not in existing_keys:
                                self.projects.append(p)
                    self.save_all()
                    self.refresh_project_list()
                    QMessageBox.information(self, 'Import Data', message)
                if hasattr(self, 'import_action'):
                    self.import_action.setEnabled(True)
            self.worker.result_signal.connect(on_result)
            self.worker.start()

    def reset_all_project_progress(self):
        for widget in self.project_item_widgets.values():
            widget.progress.setVisible(False)
            widget.progress.setValue(0)

    def update_project_progress(self, name, current, total):
        if not self.settings.get('show_inline_progress_bars', True):
            return
        widget = self.project_item_widgets.get(name)
        if widget:
            widget.progress.setVisible(True)
            widget.progress.setMaximum(total)
            widget.progress.setValue(current)
            if current >= total:
                widget.progress.setVisible(False)

    def check_all_now(self):
        import time
        print(f"[DEBUG] (check_all_now) called at {time.time()}")
        import traceback
        print('[DEBUG] (check_all_now) STACK TRACE:')
        print(''.join(traceback.format_stack()))
        print(f"[DEBUG] (check_all_now) MainWindow id: {id(self)} - method entered")
        # --- ADDED DEBUG ---
        print(f"[DEBUG] (check_all_now) [START] MainWindow id: {id(self)}")
        print(f"[DEBUG] (check_all_now) [START] self.check_worker initial: {self.check_worker}")
        print(f"[DEBUG] (check_all_now) [START] type(self.check_worker): {type(self.check_worker)}")
        if self.check_worker is not None:
            try:
                print(f"[DEBUG] (check_all_now) [START] self.check_worker.isRunning(): {self.check_worker.isRunning()}")
            except Exception as e:
                print(f"[DEBUG] (check_all_now) [START] Exception calling isRunning(): {e}")
        else:
            print(f"[DEBUG] (check_all_now) [START] self.check_worker is None, skipping isRunning() check.")
        # --- END ADDED DEBUG ---
        try:
            # Debug: print worker state before guard
            print(f"[DEBUG] (check_all_now) check_worker is {self.check_worker}, isRunning: {self.check_worker.isRunning() if self.check_worker else 'None'}")
            # Prevent double-start
            if self.check_worker is not None and self.check_worker.isRunning():
                print(f"[DEBUG] (check_all_now) Guard triggered: check_worker is running!")
                QMessageBox.warning(self, 'Check All Now', 'A check is already running.')
                return
            print('[DEBUG] Entered check_all_now')
            self.append_log('[DEBUG] Entered check_all_now')
            # Validate all project data before starting worker
            for p in self.projects:
                if not p.get('name') or not p.get('path') or not isinstance(p.get('webhooks', []), list):
                    msg = f"[ERROR] Invalid project data: {p}"
                    print(msg)
                    self.append_log(msg)
                    self.check_now_btn.setEnabled(True)
                    self.check_now_btn.setText('Check All Now')
                    return
            use_inline = self.settings.get('show_inline_progress_bars', True)
            if use_inline:
                self.reset_all_project_progress()
            self.check_now_btn.setEnabled(False)
            self.check_now_btn.setText('Checking...')
            self.check_now_cancel_btn.setEnabled(True)
            self.check_now_cancel_btn.setVisible(True)
            fmt = self.check_format_combo.currentText()
            self.check_worker = CheckAllNowWorker(self.projects, fmt)
            self.check_worker.setParent(None)
            from PyQt5.QtCore import Qt
            def on_log(msg):
                try:
                    if not self.isVisible():
                        return
                    self.append_log(msg)
                except Exception as e:
                    print(f'[ERROR] Exception in on_log: {e}')
            def on_done():
                try:
                    print(f"[DEBUG] (on_done) check_worker is {self.check_worker}, isRunning: {self.check_worker.isRunning() if self.check_worker else 'None'} (start)")
                    if not self.isVisible():
                        return
                    self.check_now_btn.setEnabled(True)
                    self.check_now_btn.setText('Check All Now')
                    self.check_now_cancel_btn.setEnabled(False)
                    self.check_now_cancel_btn.setVisible(False)
                    self.append_log('Check All Now complete.')
                    if use_inline:
                        self.reset_all_project_progress()
                    # Disconnect signals before cleanup
                    try:
                        self.check_worker.log_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        self.check_worker.done_signal.disconnect()
                    except Exception:
                        pass
                    if use_inline:
                        try:
                            self.check_worker.per_project_progress_signal.disconnect()
                        except Exception:
                            pass
                    # Robust cleanup: only wait if running, then set to None
                    if self.check_worker is not None:
                        if self.check_worker.isRunning():
                            self.check_worker.wait()
                        print(f"[DEBUG] (on_done) Setting check_worker to None")
                        self.check_worker = None
                    print(f"[DEBUG] (on_done) check_worker is {self.check_worker} (end)")
                except Exception as e:
                    print(f'[ERROR] Exception in on_done: {e}')
            self.check_worker.log_signal.connect(on_log, Qt.QueuedConnection)
            self.check_worker.done_signal.connect(on_done, Qt.QueuedConnection)
            if use_inline:
                self.check_worker.per_project_progress_signal.connect(self.update_project_progress, Qt.QueuedConnection)
            self.check_worker.start()
        except Exception as e:
            tb = traceback.format_exc()
            self.append_log(f'[FATAL ERROR] Exception in check_all_now: {e}\n{tb}')
            self.check_now_btn.setEnabled(True)
            self.check_now_btn.setText('Check All Now')
            self.check_now_cancel_btn.setEnabled(False)
            self.check_now_cancel_btn.setVisible(False)
            self.check_worker = None

    def cancel_check_all_now(self):
        print(f"[DEBUG] (cancel_check_all_now) check_worker is {self.check_worker}, isRunning: {self.check_worker.isRunning() if self.check_worker else 'None'}")
        if self.check_worker is not None:
            self.check_worker.stop()
            self.check_now_cancel_btn.setEnabled(False)
            self.append_log('Check All Now cancelled by user.')
            print(f"[DEBUG] (cancel_check_all_now) Setting check_worker to None")
            self.check_worker = None

    def test_all_status(self):
        use_inline = self.settings.get('show_inline_progress_bars', True)
        if use_inline:
            self.reset_all_project_progress()
        self.test_all_btn.setEnabled(False)
        self.test_all_btn.setText('Testing...')
        self.worker = TestAllStatusWorker(self.projects)
        def on_status(project_statuses):
            self.project_statuses = project_statuses
            self.refresh_project_list()
        def on_done():
            self.test_all_btn.setEnabled(True)
            self.test_all_btn.setText('Test All')
            self.append_log('Test All complete.')
            if use_inline:
                self.reset_all_project_progress()
            self.worker = None
        self.worker.status_signal.connect(on_status)
        self.worker.done_signal.connect(on_done)
        if use_inline:
            self.worker.per_project_progress_signal.connect(self.update_project_progress)
        self.worker.start()

    def test_selected_project(self):
        row = self.project_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, 'Test Project', 'Please select a project to test.')
            return
        project = self.projects[row]
        self.project_test_btn.setEnabled(False)
        self.project_test_btn.setText('Testing...')
        use_inline = self.settings.get('show_inline_progress_bars', True)
        if use_inline:
            self.reset_all_project_progress()
        self.worker = TestSelectedProjectWorker(project)
        def on_status(name, status):
            if not hasattr(self, 'project_statuses'):
                self.project_statuses = {}
            self.project_statuses[name] = status
            self.refresh_project_list()
        def on_done():
            self.project_test_btn.setEnabled(True)
            self.project_test_btn.setText('Test Selected')
            self.append_log('Test Selected complete.')
            if use_inline:
                self.reset_all_project_progress()
            self.worker = None
        self.worker.status_signal.connect(on_status)
        self.worker.done_signal.connect(on_done)
        if use_inline:
            self.worker.per_project_progress_signal.connect(self.update_project_progress)
        self.worker.start()

    def set_always_on_top(self, checked):
        self.settings['always_on_top'] = checked
        self.save_all()
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def set_dark_mode(self, checked):
        self.settings['dark_mode'] = checked
        self.save_all()
        if checked:
            dark_stylesheet = """
                QWidget { background-color: #232629; color: #f0f0f0; }
                QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget, QTabWidget::pane { background: #2b2b2b; color: #f0f0f0; }
                QPushButton { background-color: #444; color: #f0f0f0; border: 1px solid #333; }
                QPushButton:hover { background-color: #555; }
                QMenuBar, QMenu { background: #232629; color: #f0f0f0; }
                QMenu::item:selected { background: #444; }
                QGroupBox { border: 1px solid #444; margin-top: 6px; }
                QGroupBox:title { subcontrol-origin: margin; left: 7px; padding: 0 3px 0 3px; }
                QCheckBox, QLabel { color: #f0f0f0; }
                QStatusBar { background: #232629; color: #f0f0f0; }
            """
            self.setStyleSheet(dark_stylesheet)
        else:
            self.setStyleSheet("")

    def project_item_clicked(self, item):
        # Optionally, could auto-select the project for testing
        pass

    def update_monitor_status(self, running):
        if running:
            self.monitor_status_label.setText('<span style="color:green;font-weight:bold;">Monitoring: ON</span>')
        else:
            self.monitor_status_label.setText('<span style="color:red;font-weight:bold;">Monitoring: OFF</span>')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 