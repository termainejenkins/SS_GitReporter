import os
import time
from git import Repo
from discord_webhook import DiscordWebhook, DiscordEmbed
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

class GitReporter:
    def __init__(self):
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.repo_path = os.getenv('REPO_PATH')
        self.repo = None
        self.last_commit_hash = None
        
        # UE4 specific file extensions
        self.ue4_extensions = {
            'blueprints': ['.uasset'],
            'c++': ['.cpp', '.h'],
            'content': ['.umap', '.uproject'],
            'config': ['.ini', '.config'],
            'materials': ['.uasset'],
            'animations': ['.uasset'],
        }
    
    def connect_to_repo(self):
        """Initialize connection to git repository"""
        try:
            self.repo = Repo(self.repo_path)
            print(f"Successfully connected to repo at {self.repo_path}")
            return True
        except Exception as e:
            print(f"Error connecting to repo: {str(e)}")
            return False

    def categorize_changes(self, commit):
        """Categorize changed files based on UE4 file types"""
        changes = {
            'blueprints': [],
            'c++': [],
            'content': [],
            'config': [],
            'materials': [],
            'animations': [],
            'other': []
        }
        
        for item in commit.stats.files:
            ext = os.path.splitext(item)[1].lower()
            categorized = False
            
            for category, extensions in self.ue4_extensions.items():
                if ext in extensions:
                    changes[category].append(item)
                    categorized = True
                    break
            
            if not categorized:
                changes['other'].append(item)
        
        return changes

    def format_discord_message(self, commit, changes):
        """Format commit information for Discord webhook"""
        embed = DiscordEmbed(
            title=f"New Commit: {commit.hexsha[:7]}",
            description=commit.message,
            color=0x00ff00
        )
        
        embed.add_embed_field(
            name="Author",
            value=f"{commit.author.name} <{commit.author.email}>",
            inline=True
        )
        
        embed.add_embed_field(
            name="Date",
            value=datetime.fromtimestamp(commit.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
            inline=True
        )
        
        # Add categorized changes
        for category, files in changes.items():
            if files:
                embed.add_embed_field(
                    name=f"{category.capitalize()} Changes",
                    value="\n".join([f"• {f}" for f in files[:5]]) + 
                          (f"\n... and {len(files) - 5} more" if len(files) > 5 else ""),
                    inline=False
                )
        
        return embed

    def send_to_discord(self, embed):
        """Send formatted message to Discord"""
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            webhook.add_embed(embed)
            response = webhook.execute()
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending to Discord: {str(e)}")
            return False

    def monitor_repo(self):
        """Main loop to monitor repository for changes"""
        if not self.connect_to_repo():
            return
        
        print("Starting repository monitoring...")
        
        while True:
            try:
                current_commit = self.repo.head.commit
                
                if current_commit.hexsha != self.last_commit_hash:
                    print(f"New commit detected: {current_commit.hexsha[:7]}")
                    
                    # Analyze and categorize changes
                    changes = self.categorize_changes(current_commit)
                    
                    # Format and send Discord message
                    embed = self.format_discord_message(current_commit, changes)
                    if self.send_to_discord(embed):
                        print("Successfully sent commit information to Discord")
                    
                    self.last_commit_hash = current_commit.hexsha
                
                # Wait before next check
                time.sleep(30)
                
                # Fetch latest changes
                self.repo.remotes.origin.fetch()
                
            except Exception as e:
                print(f"Error during monitoring: {str(e)}")
                time.sleep(60)  # Wait longer if there's an error

if __name__ == "__main__":
    reporter = GitReporter()
    reporter.monitor_repo() 