import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMenuBar, QAction, QSystemTrayIcon, QStyle, QMenu,
    QDialog, QLineEdit, QComboBox, QFormLayout, QMessageBox, QListWidgetItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

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

        # In-memory project storage (to be replaced with persistent config)
        self.projects = []

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
        btn_layout.addWidget(self.add_project_btn)
        btn_layout.addWidget(self.remove_project_btn)
        main_layout.addLayout(btn_layout)

        # Placeholder for webhook management and logs
        main_layout.addWidget(QLabel('Webhooks and Logs (coming soon)'))

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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

        # TODO: Add webhook management UI
        # TODO: Add background monitoring logic
        # TODO: Add log viewer
        # TODO: Persist config to JSON
        # TODO: Implement message formatting logic

    def open_add_project_dialog(self):
        dialog = ProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.projects.append(data)
            self.refresh_project_list()
            QMessageBox.information(self, 'Project Added', f"Project '{data['name']}' added with {len(data['webhooks'])} webhook{'s' if len(data['webhooks']) != 1 else ''}.")

    def remove_selected_project(self):
        row = self.project_list.currentRow()
        if row >= 0:
            removed = self.projects.pop(row)
            self.refresh_project_list()
            QMessageBox.information(self, 'Project Removed', f"Project '{removed['name']}' removed.")
        else:
            QMessageBox.warning(self, 'No Selection', 'Please select a project to remove.')

    def refresh_project_list(self):
        self.project_list.clear()
        for proj in self.projects:
            wh_count = len(proj.get('webhooks', []))
            self.project_list.addItem(f"{proj['name']} ({wh_count} webhook{'s' if wh_count != 1 else ''})")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 