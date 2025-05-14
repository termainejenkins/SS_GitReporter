# UE4 Git Reporter

An automated tool that monitors your Unreal Engine 4 project's git repository and reports changes to Discord via webhooks.

---

## 🚀 Upcoming: UE4 Git Reporter Desktop (PyQt5)
A modern desktop application for managing and monitoring multiple Unreal Engine project repositories, with advanced Discord integration and flexible UI options.

### Planned Features
- **Multi-project support:** Monitor several git repositories at once
- **Multi-webhook support:** Send reports to multiple Discord channels per project
- **Visual configuration:** Add/edit/remove projects and webhooks via the app
- **Start/stop monitoring:** Control monitoring from the UI
- **System tray integration:** Run in background or as a visible window
- **Manual reporting:** Send a report on demand
- **Log viewer:** See activity and errors in the app
- **Customizable filters:** Manage ignore patterns per project
- **Theme support:** Light/dark mode

### Roadmap
1. PyQt5 main window with project/webhook management
2. System tray and background monitoring
3. Integration of git monitoring and Discord reporting
4. Enhanced UI/UX and extra features

---

## Features (Current CLI Version)
- Automatic git change detection
- Discord webhook integration
- Configurable monitoring intervals
- Filtered reporting (ignores binary files, temporary directories)
- Real-time change notifications

## Credits
Created by **Termaine Jenkins** (TJ)  
SENTIENT SOLUTIONS LLC

## Quick Start (CLI Version)
1. Ensure Python 3.x is installed
2. Install dependencies: `py -m pip install -r requirements.txt`
3. Configure `config.json` with your:
   - UE4 project path
   - Discord webhook URL
4. Run: `py main.py`

## Documentation
- [Project Requirements](docs/PROJECT_REQUIREMENTS.md)
- [Design Decisions](docs/DESIGN_DECISIONS.md)
- [Development Log](docs/DEVLOG.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

## License
Copyright © 2024 SENTIENT SOLUTIONS LLC. All rights reserved. 