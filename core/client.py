#!/usr/bin/env python3
"""
Fixed Telegram Music Userbot Client
"""

import asyncio
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import SQLiteSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from .database import Database
from .music import MusicManager

logger = logging.getLogger(__name__)


class MusicUserbot:
    def __init__(self):
        self.version = "2.0.0-fixed"
        self.client = None
        self.music = None
        self.database = Database()
        
        # Paths
        self.data_dir = Path("data")
        self.session_file = self.data_dir / "userbot.session"
        self.credentials_file = self.data_dir / "credentials.json"
        
        # Ensure data directory exists
        self.data_dir.mkdir(exist_ok=True)
        
        # State
        self.is_authenticated = False
        self.me = None
        self.pending_code_hash = None

    def has_saved_credentials(self) -> bool:
        """Check if we have saved API credentials"""
        return self.credentials_file.exists()

    async def auto_initialize(self) -> bool:
        """Auto-initialize with saved credentials"""
        try:
            if not self.has_saved_credentials():
                return False
                
            credentials = self.database.get_credentials()
            if not credentials:
                return False
                
            await self.initialize(credentials['api_id'], credentials['api_hash'])
            logger.info("✅ Auto-initialized with saved credentials")
            return True
            
        except Exception as e:
            logger.error(f"❌ Auto-initialization failed: {e}")
            return False

    async def initialize(self, api_id: int, api_hash: str):
        """Initialize userbot with API credentials"""
        try:
            # Save credentials
            self.database.save_credentials(api_id, api_hash)
            
            # Create Telegram client
            self.client = TelegramClient(
                str(self.session_file),
                api_id,
                api_hash,
                device_model="Music Userbot",
                system_version="2.0.0",
                app_version="2.0.0",
                lang_code="en",
                system_lang_code="en"
            )
            
            logger.info("✅ Userbot initialized with API credentials")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize userbot: {e}")
            raise

    async def start(self, force_auth: bool = False) -> bool:
        """Start the userbot"""
        try:
            if not self.client:
                logger.error("❌ Client not initialized")
                return False
            
            await self.client.connect()
            
            # Check if already authenticated
            if await self.client.is_user_authorized() and not force_auth:
                self.me = await self.client.get_me()
                self.is_authenticated = True
                
                # Initialize music manager
                self.music = MusicManager(self.client)
                
                # Set up event handlers
                self._setup_handlers()
                
                logger.info(f"✅ Authenticated as {self.me.first_name} (@{self.me.username})")
                return True
            else:
                logger.info("⏳ Authentication required")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start userbot: {e}")
            return False

    async def send_code(self, phone: str) -> dict:
        """Send verification code to phone"""
        try:
            if not self.client or not self.client.is_connected():
                await self.client.connect()
            
            result = await self.client.send_code_request(phone)
            self.pending_code_hash = result.phone_code_hash
            
            logger.info(f"📱 Verification code sent to {phone}")
            return {
                'success': True,
                'message': f'Verification code sent to {phone}'
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send code: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def verify_code(self, code: str, password: Optional[str] = None) -> dict:
        """Verify phone code and login"""
        try:
            if not self.pending_code_hash:
                return {
                    'success': False,
                    'error': 'No pending verification code'
                }
            
            try:
                await self.client.sign_in(code=code, phone_code_hash=self.pending_code_hash)
            except SessionPasswordNeededError:
                if not password:
                    return {
                        'success': False,
                        'error': '2FA_REQUIRED',
                        'requires_password': True
                    }
                await self.client.sign_in(password=password)
            
            # Get user info
            self.me = await self.client.get_me()
            self.is_authenticated = True
            
            # Initialize music manager
            self.music = MusicManager(self.client)
            
            # Set up event handlers
            self._setup_handlers()
            
            logger.info(f"✅ Successfully authenticated as {self.me.first_name}")
            
            return {
                'success': True,
                'message': 'Successfully authenticated',
                'user': {
                    'id': self.me.id,
                    'first_name': self.me.first_name,
                    'last_name': getattr(self.me, 'last_name', None),
                    'username': getattr(self.me, 'username', None),
                    'phone': getattr(self.me, 'phone', None)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to verify code: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _setup_handlers(self):
        """Set up message handlers"""
        
        @self.client.on(events.NewMessage(pattern=r'\.join'))
        async def join_handler(event):
            """Join voice chat"""
            try:
                chat_id = event.chat_id
                success = await self.music.join_voice_chat(chat_id)
                if success:
                    await event.respond("✅ Joined voice chat!")
                else:
                    await event.respond("❌ Failed to join voice chat")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.leave'))
        async def leave_handler(event):
            """Leave voice chat"""
            try:
                chat_id = event.chat_id
                success = await self.music.leave_voice_chat(chat_id)
                if success:
                    await event.respond("✅ Left voice chat!")
                else:
                    await event.respond("❌ Failed to leave voice chat")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.play (.+)'))
        async def play_handler(event):
            """Play music from URL or reply to audio"""
            try:
                source = event.pattern_match.group(1)
                chat_id = event.chat_id
                reply = await event.get_reply_message()
                
                # Check if user is joined to voice chat
                if chat_id not in self.music.group_calls:
                    await event.respond("❌ Not joined to voice chat. Use .join first")
                    return
                
                await event.respond("🎵 Downloading...")
                
                # Play from file if replying to audio
                if reply and reply.file and reply.file.mime_type and reply.file.mime_type.startswith('audio'):
                    await event.edit("⬇️ Downloading audio file...")
                    audio_file = await reply.download_media()
                    await event.edit("🔄 Converting...")
                    success = await self.music.play_from_file(chat_id, audio_file)
                else:
                    # Play from URL
                    await event.edit("⬇️ Downloading from URL...")
                    success = await self.music.play_audio(chat_id, source)
                
                if success:
                    await event.edit("▶️ Playing...")
                else:
                    await event.edit("❌ Failed to play audio")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.stop'))
        async def stop_handler(event):
            """Stop playback"""
            try:
                chat_id = event.chat_id
                success = await self.music.stop_audio(chat_id)
                if success:
                    await event.respond("⏹️ Stopped playback")
                else:
                    await event.respond("❌ Failed to stop playback")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.pause'))
        async def pause_handler(event):
            """Pause playback"""
            try:
                chat_id = event.chat_id
                success = await self.music.pause_audio(chat_id)
                if success:
                    await event.respond("⏸️ Paused playback")
                else:
                    await event.respond("❌ Failed to pause playback")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.resume'))
        async def resume_handler(event):
            """Resume playback"""
            try:
                chat_id = event.chat_id
                success = await self.music.resume_audio(chat_id)
                if success:
                    await event.respond("▶️ Resumed playback")
                else:
                    await event.respond("❌ Failed to resume playback")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.mute'))
        async def mute_handler(event):
            """Mute audio"""
            try:
                chat_id = event.chat_id
                success = await self.music.mute_audio(chat_id)
                if success:
                    await event.respond("🔇 Muted!")
                else:
                    await event.respond("❌ Failed to mute")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.unmute'))
        async def unmute_handler(event):
            """Unmute audio"""
            try:
                chat_id = event.chat_id
                success = await self.music.unmute_audio(chat_id)
                if success:
                    await event.respond("🔊 Unmuted!")
                else:
                    await event.respond("❌ Failed to unmute")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.replay'))
        async def replay_handler(event):
            """Replay current audio"""
            try:
                chat_id = event.chat_id
                success = await self.music.replay_audio(chat_id)
                if success:
                    await event.respond("🔄 Replaying...")
                else:
                    await event.respond("❌ Failed to replay")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.shazam'))
        async def shazam_handler(event):
            """Recognize music from reply"""
            try:
                reply = await event.get_reply_message()
                if not reply or not reply.file or not reply.file.mime_type or not reply.file.mime_type.startswith('audio'):
                    await event.respond("❌ Reply to an audio file")
                    return
                
                await event.respond("⬇️ Downloading...")
                audio_bytes = await reply.download_media(bytes)
                
                await event.edit("🎵 Recognizing...")
                result = await self.music.shazam_recognize(audio_bytes)
                
                if result:
                    response = f"🎵 **Recognized track:**\n🎤 **{result['title']}**\n👤 **{result['artist']}**"
                    await event.edit(response)
                else:
                    await event.edit("❌ Could not recognize track")
                    
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.debug'))
        async def debug_handler(event):
            """Debug info"""
            try:
                debug_info = self.music.debug_info()
                await event.respond(f"🐛 {debug_info}")
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

        @self.client.on(events.NewMessage(pattern=r'\.status'))
        async def status_handler(event):
            """Get status"""
            try:
                chat_id = event.chat_id
                status = self.music.get_status(chat_id)
                
                status_text = f"""
🎵 **Music Bot Status**
🔗 Connected: {'✅' if status['connected'] else '❌'}
📱 Chat ID: `{status['chat_id']}`
🎵 Group Call: {'✅' if status['has_group_call'] else '❌'}
                """
                await event.respond(status_text)
            except Exception as e:
                await event.respond(f"❌ Error: {e}")

    async def run_until_disconnected(self):
        """Run userbot until disconnected"""
        try:
            logger.info("🎵 Music userbot is now running...")
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Error while running: {e}")

    async def disconnect(self):
        """Disconnect userbot"""
        try:
            if self.music:
                # Leave all voice chats
                for chat_id in list(self.music.group_calls.keys()):
                    await self.music.leave_voice_chat(int(chat_id))
            
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                
            logger.info("✅ Userbot disconnected")
            
        except Exception as e:
            logger.error(f"❌ Error disconnecting: {e}")

    def get_status(self) -> dict:
        """Get userbot status"""
        return {
            "authenticated": self.is_authenticated,
            "connected": self.client.is_connected() if self.client else False,
            "version": self.version,
            "user": {
                "id": self.me.id if self.me else None,
                "first_name": self.me.first_name if self.me else None,
                "username": getattr(self.me, 'username', None) if self.me else None
            } if self.me else None
        }