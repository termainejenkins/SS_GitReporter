import logging
import time
import os
import sys
from git_reporter.config_manager import ConfigManager
from git_reporter.monitor import GitMonitor
from git_reporter.discord_client import DiscordClient
from dotenv import load_dotenv

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
    required_fields = ['project_path']
    for field in required_fields:
        if not config.get(field):
            raise ValueError(f"Missing required configuration: {field}")

def main():
    """Main application entry point with enhanced error handling."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load and validate configuration (now robust: atomic save, backup, versioning, validation)
        load_dotenv()
        config_manager = ConfigManager()
        config = config_manager.config
        validate_config(config)  # This is now handled in config_utils, but keep for clarity
        
        # Show log if requested
        if config.get('start_with_log_open', False):
            log_path = 'logs/reporter.log'
            if os.path.exists(log_path):
                print("\n--- Reporter Log (last 20 lines) ---")
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines[-20:]:
                        print(line.rstrip())
                print("--- End of Log ---\n")
            else:
                print("Log file does not exist yet.")

        # Respect auto_start_monitoring
        if not config.get('auto_start_monitoring', True):
            print("Auto start monitoring is disabled. Exiting.")
            return
        
        # Initialize components with error handling
        try:
            monitor = GitMonitor(
                config['project_path'],
                config.get('ignored_files', [])
            )
        except ValueError as e:
            logger.error(f"Git repository error: {str(e)}")
            sys.exit(1)
        
        discord = DiscordClient(os.getenv('DISCORD_WEBHOOK_URL'))
        
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
                
        # If you change config at runtime, call config_manager.save_config()
                
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 