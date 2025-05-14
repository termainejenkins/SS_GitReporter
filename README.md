# UE4 Git Reporter

An automated tool that monitors your Unreal Engine 4 project's git repository and reports changes to Discord via webhooks.

## Features
- Automatic git change detection
- Discord webhook integration
- Configurable monitoring intervals
- Filtered reporting (ignores binary files, temporary directories)
- Real-time change notifications

## Credits
Created by **Termaine Jenkins** (TJ)  
SENTIENT SOLUTIONS LLC

## Quick Start
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