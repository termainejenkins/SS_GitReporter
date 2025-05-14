# Project Requirements

## User Stories

### Core Features

1. **Git Monitoring**
   ```
   As a UE4 developer
   I want the app to monitor my local git repository
   So that I can track changes automatically
   ```
   - Must detect new commits
   - Must handle different types of changes (add, modify, delete)
   - Must respect .gitignore rules

2. **Discord Integration**
   ```
   As a team member
   I want commit information sent to Discord
   So that everyone stays informed of project changes
   ```
   - Must format messages clearly
   - Must include relevant commit details
   - Must handle connection issues gracefully

3. **Change Filtering**
   ```
   As a project manager
   I want to filter out noise from binary and temporary files
   So that we only see meaningful code changes
   ```
   - Must ignore *.uasset files by default
   - Must ignore Saved/ and Intermediate/ directories
   - Must allow customizable ignore patterns

4. **Configurable Monitoring**
   ```
   As a system administrator
   I want to configure monitoring intervals
   So that I can control server load and notification frequency
   ```
   - Must allow custom check intervals
   - Must run reliably in background
   - Must handle system restarts gracefully

### Future Enhancements

5. **Enhanced Reporting**
   ```
   As a technical lead
   I want detailed change statistics
   So that I can track project progress better
   ```
   - Could include file type statistics
   - Could track lines changed
   - Could categorize changes by component

6. **Multi-Branch Support**
   ```
   As a developer
   I want to monitor multiple branches
   So that I can track feature development separately
   ```
   - Could track multiple branches
   - Could compare branch differences
   - Could notify on merge conflicts 