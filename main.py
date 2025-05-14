import logging
import time
import os
from git_reporter.config_manager import ConfigManager
from git_reporter.monitor import GitMonitor
from git_reporter.discord_client import DiscordClient

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/reporter.log'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = ConfigManager()
        
        # Initialize components
        monitor = GitMonitor(
            config.get('project_path'),
            config.get('ignored_files')
        )
        
        discord = DiscordClient(config.get('discord_webhook_url'))
        
        logger.info("UE4 Git Reporter started")
        
        while True:
            try:
                # Generate and send report
                report = monitor.generate_report()
                if report:
                    discord.send_message(report)
                
                # Wait for next check
                time.sleep(config.get('check_interval_minutes') * 60)
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying
                
    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")

if __name__ == "__main__":
    main() 