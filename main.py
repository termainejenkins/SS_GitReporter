import logging
import time
import os
import sys
from git_reporter.config_manager import ConfigManager
from git_reporter.monitor import GitMonitor
from git_reporter.discord_client import DiscordClient

def setup_logging():
    """Set up logging configuration."""
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

def validate_config(config):
    """Validate configuration settings."""
    required_fields = ['project_path', 'discord_webhook_url']
    for field in required_fields:
        if not config.get(field):
            raise ValueError(f"Missing required configuration: {field}")

def main():
    """Main application entry point with enhanced error handling."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load and validate configuration
        config = ConfigManager().config
        validate_config(config)
        
        # Initialize components with error handling
        try:
            monitor = GitMonitor(
                config['project_path'],
                config.get('ignored_files', [])
            )
        except ValueError as e:
            logger.error(f"Git repository error: {str(e)}")
            sys.exit(1)
        
        discord = DiscordClient(config['discord_webhook_url'])
        
        # Send initial status message
        startup_msg = f"UE4 Git Reporter started\nMonitoring: {config['project_path']}"
        if not discord.send_message(startup_msg):
            logger.warning("Failed to send startup message to Discord")
        
        logger.info(startup_msg)
        
        # Main monitoring loop
        check_interval = config.get('check_interval_minutes', 30) * 60
        while True:
            try:
                report = monitor.check_for_changes()
                if report:
                    if not discord.send_message(report):
                        logger.error("Failed to send report to Discord")
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logger.info("Shutting down gracefully...")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(60)  # Wait before retrying
                
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 