import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QMenuBar, QAction, QSystemTrayIcon, QStyle, QMenu,
    QDialog, QLineEdit, QComboBox, QFormLayout, QMessageBox
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

class ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Project')
        self.setModal(True)
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.path_edit = QLineEdit()
        self.webhook_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(MESSAGE_FORMATS)

        layout.addRow('Project Name:', self.name_edit)
        layout.addRow('Project Path:', self.path_edit)
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
            'name': self.name_edit.text(),
            'path': self.path_edit.text(),
            'webhook': self.webhook_edit.text(),
            'format': self.format_combo.currentText()
        }

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('UE4 Git Reporter Desktop')
        self.setGeometry(100, 100, 800, 500)
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)))

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
        # TODO: Connect remove_project_btn

        # TODO: Add webhook management UI
        # TODO: Add background monitoring logic
        # TODO: Add log viewer
        # TODO: Persist config to JSON
        # TODO: Implement message formatting logic

    def open_add_project_dialog(self):
        dialog = ProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            # For now, just add the project name to the list
            self.project_list.addItem(f"{data['name']} ({data['format']})")
            # TODO: Save project data and update config
            QMessageBox.information(self, 'Project Added', f"Project '{data['name']}' added with format: {data['format']}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 