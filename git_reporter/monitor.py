import subprocess
import os
import logging
from datetime import datetime
from typing import Tuple, List, Optional

class GitMonitor:
    def __init__(self, project_path: str, ignored_files: List[str]):
        self.project_path = project_path
        self.ignored_files = ignored_files
        self.logger = logging.getLogger(__name__)

    def _run_git_command(self, command: List[str]) -> Optional[str]:
        try:
            os.chdir(self.project_path)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command failed: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Error running git command: {str(e)}")
            return None

    def get_changes(self) -> Tuple[Optional[str], Optional[str]]:
        status = self._run_git_command(['git', 'status', '--porcelain'])
        
        commits = self._run_git_command([
            'git', 'log',
            '--pretty=format:%h - %s - by %an (%ad)',
            '--date=relative',
            '-n', '5'
        ])
        
        return status, commits

    def generate_report(self) -> Optional[str]:
        status, commits = self.get_changes()
        
        if status is None and commits is None:
            self.logger.error("Failed to generate report - no git data available")
            return None

        message = [
            "**🎮 UE4.27 Project Update**",
            f"*Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        ]

        if status:
            message.extend([
                "**📝 Uncommitted Changes:**",
                "```",
                status,
                "```\n"
            ])

        if commits:
            message.extend([
                "**🔄 Recent Commits:**",
                "```",
                commits,
                "```"
            ])

        return '\n'.join(message) 