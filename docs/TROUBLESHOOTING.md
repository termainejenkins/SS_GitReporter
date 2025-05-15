# Troubleshooting Guide

## Common Issues

### 1. Path Not Found Error
**Problem**: Error message `The system cannot find the path specified: '{path}'`
```
ERROR - Error running git command: [WinError 3] The system cannot find the path specified
```
**Solution**:
1. Verify the path in `config.json` exists
2. Ensure the path uses forward slashes (/) or escaped backslashes (\\)
3. Check if the path points to a valid git repository
4. Verify you have read permissions for the directory

### 2. Discord Webhook Issues
**Problem**: Messages not appearing in Discord
**Solution**:
1. Verify webhook URL is correct
2. Check Discord server permissions
3. Ensure webhook hasn't been rate limited
4. Test webhook using curl or Postman

### 3. Python Installation Issues
**Problem**: `python` or `pip` commands not recognized
**Solution**:
1. Verify Python is installed: `py --version`
2. Add Python to PATH during installation
3. Use `py -m pip` instead of `pip` on Windows
4. Restart terminal after installation

### 4. Git Integration Problems
**Problem**: Git commands failing or not detecting changes
**Solution**:
1. Verify git is installed: `git --version`
2. Check if directory is a git repository: `git status`
3. Ensure git user is configured:
   ```
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```
4. Check repository permissions

### 5. Background Process Issues
**Problem**: Application stops monitoring after some time
**Solution**:
1. Check system logs for errors
2. Verify Python process is running
3. Ensure sufficient system resources
4. Consider using a process manager

### 6. Config Corruption or Loss
**Problem**: The app fails to start or reports config file errors
**Solution**:
1. The app automatically creates a backup of your config file before saving (`*.bak`).
2. If the config is corrupted, the app will attempt to restore from backup or use default settings.
3. You can manually restore by renaming the backup file to replace the corrupted config.
4. Config files are validated on load; if invalid, the app will attempt to repair or prompt you for action.

## Reporting New Issues
When reporting issues:
1. Check logs in the `logs` directory
2. Include error messages
3. Describe steps to reproduce
4. List your system configuration:
   - OS version
   - Python version
   - Git version 