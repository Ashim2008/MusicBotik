#!/usr/bin/env python3
"""
Entry point for Fixed Music Userbot
"""

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path

# Add project to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import components
from core.client import MusicUserbot
from web.server import WebServer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Fixed Telegram Music Userbot')
    parser.add_argument('--port', type=int, default=5000, help='Web interface port')
    parser.add_argument('--no-web', action='store_true', help='Disable web interface')
    parser.add_argument('--auth', action='store_true', help='Force re-authentication')
    
    # Override port from environment
    port = int(os.environ.get('PORT', 5000))
    if '--port' not in sys.argv and port != 5000:
        sys.argv.extend(['--port', str(port)])
    
    args = parser.parse_args()

    # Initialize userbot
    userbot = MusicUserbot()
    
    # Initialize web server variables
    web_server = None
    web_task = None
    
    if not args.no_web:
        web_server = WebServer(userbot, port=args.port)
    
    try:
        logger.info("🎵 Starting Fixed Telegram Music Userbot...")
        
        if not args.no_web and web_server:
            # Start web server in background
            web_task = asyncio.create_task(web_server.run_forever())
            logger.info(f"🌐 Web interface available at http://0.0.0.0:{args.port}")
        
        # Try to auto-initialize and start userbot if credentials and session exist
        if userbot.has_saved_credentials() and userbot.session_file.exists():
            try:
                # Auto-initialize with saved credentials
                if not userbot.client:
                    await userbot.auto_initialize()
                
                success = await userbot.start(force_auth=args.auth)
                if success:
                    logger.info("✅ Userbot is running. Press Ctrl+C to stop.")
                    await userbot.run_until_disconnected()
                else:
                    logger.info("⏳ Authentication required. Use web interface to login.")
            except Exception as e:
                logger.info(f"⏳ Auto-start failed: {e}. Use web interface to setup.")
        elif userbot.client:
            try:
                success = await userbot.start(force_auth=args.auth)
                if success:
                    logger.info("✅ Userbot is running. Press Ctrl+C to stop.")
                    await userbot.run_until_disconnected()
                else:
                    logger.info("⏳ Authentication required. Use web interface to login.")
            except RuntimeError:
                logger.info("⏳ Userbot not initialized. Use web interface to setup.")
        else:
            logger.info("⏳ Userbot not initialized. Use web interface to setup.")
        
        # Keep web server running if userbot not started
        if not args.no_web and web_task:
            logger.info("🌐 Web interface is running. Press Ctrl+C to stop.")
            try:
                await web_task
            except asyncio.CancelledError:
                pass
        
    except KeyboardInterrupt:
        logger.info("🛑 Stopping userbot...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        if userbot and userbot.client:
            await userbot.disconnect()
        if not args.no_web and web_server:
            await web_server.stop()


if __name__ == '__main__':
    asyncio.run(main())