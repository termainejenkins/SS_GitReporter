import subprocess
import os
import logging
from datetime import datetime
from typing import Tuple, List, Optional

class GitMonitor:
    def __init__(self, project_path: str, ignored_files: List[str]):
        self.project_path = self._normalize_path(project_path)
        self.ignored_files = ignored_files
        self.logger = logging.getLogger(__name__)
        self._validate_repository()

    def _normalize_path(self, path: str) -> str:
        """Normalize path to use correct system separators."""
        return os.path.normpath(path)

    def _validate_repository(self) -> None:
        """Validate git repository and path existence."""
        if not os.path.exists(self.project_path):
            raise ValueError(f"Project path does not exist: {self.project_path}")
        
        git_dir = os.path.join(self.project_path, '.git')
        if not os.path.exists(git_dir):
            raise ValueError(f"Not a git repository: {self.project_path}")

    def _run_git_command(self, command: List[str]) -> Optional[str]:
        """Run a git command with better error handling."""
        try:
            if not os.path.exists(self.project_path):
                raise FileNotFoundError(f"Project path not found: {self.project_path}")

            os.chdir(self.project_path)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command failed: {e.stderr.strip()}")
            return None
        except FileNotFoundError as e:
            self.logger.error(f"Path error: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error running git command: {str(e)}")
            return None

    def check_for_changes(self) -> Optional[str]:
        """Check for new commits with enhanced error handling."""
        try:
            # Get latest commit
            latest_commit = self._run_git_command(['git', 'log', '-1', '--oneline'])
            if not latest_commit:
                return None

            # Get modified files
            modified_files = self._run_git_command(['git', 'status', '--porcelain'])
            
            # Generate report
            report = []
            report.append(f"Latest commit: {latest_commit}")
            if modified_files:
                report.append("\nModified files:")
                for line in modified_files.split('\n'):
                    if line.strip():
                        report.append(f"- {line.strip()}")

            return '\n'.join(report)
        except Exception as e:
            self.logger.error(f"Failed to generate report: {str(e)}")
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