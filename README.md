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
- **Export/Import:** Easily back up or transfer your project/webhook configuration
- **Advanced summaries:** Choose between local smart summaries and LLM-powered summaries (see below)

### LLM Integration (Local & Cloud)
- **Local LLM (Recommended):**
  - Integrate with [Ollama](https://ollama.com/) or [LM Studio](https://lmstudio.ai/) to run open-source LLMs (like Mistral, Llama 2, Phi) on your own machine.
  - No API key or internet required after model download.
  - The app can start/stop the LLM server for you, or detect if it's already running.
  - Select "LLM Summary (Local)" in the format dropdown to generate natural-language summaries of your git changes.
  - **Privacy:** No data leaves your machine.
- **Cloud LLM (Optional/Future):**
  - Optionally, connect to OpenAI, Gemini, or other cloud LLMs with your own API key.
  - Useful for even more advanced summaries if desired.
- **Fallback:** If no LLM is available, the app uses its built-in smart local summary.

### Privacy & User Control
- **Local-first:** All monitoring and summaries are local by default.
- **User control:** You decide if/when to use LLMs, and whether the app should start/stop the LLM server automatically.
- **No cloud dependency** unless you explicitly enable it.

### Roadmap
1. PyQt5 main window with project/webhook management
2. System tray and background monitoring
3. Integration of git monitoring and Discord reporting
4. Enhanced UI/UX and extra features
5. **LLM-powered summaries (local and cloud)**

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