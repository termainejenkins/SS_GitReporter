# Git Reporter for UE4.27

An automated tool that monitors your Unreal Engine 4.27 git repository and sends commit notifications to Discord via webhooks.

## Features
- Monitors git repository changes
- Generates detailed commit summaries
- Automatically detects UE4.27 specific file changes
- Sends formatted messages to Discord via webhooks

## Setup
1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your Discord webhook URL:
   ```
   DISCORD_WEBHOOK_URL=your_webhook_url_here
   REPO_PATH=path_to_your_ue4_project
   ```
4. Run the script:
   ```bash
   python git_reporter.py
   ```

## Configuration
- The script can be configured to run on startup or as a scheduled task
- Customize the commit message format in the config.py file
- Add additional file type monitoring in the file_types.py 