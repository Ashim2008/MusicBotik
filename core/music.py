#!/usr/bin/env python3
"""
Fixed Music Manager for Telegram Userbot - Based on working VoiceMod
Working with pytgcalls 2.1.0 GroupCallFactory API
"""

import io
import os
import re
import logging
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

import ffmpeg
from yt_dlp import YoutubeDL
from ShazamAPI import Shazam

# Fallback imports for pytgcalls
try:
    from pytgcalls import GroupCallFactory
    from pytgcalls.implementation.group_call_file import GroupCallFile
    PYTGCALLS_AVAILABLE = True
except ImportError:
    logger.warning("pytgcalls not available - voice chat features disabled")
    PYTGCALLS_AVAILABLE = False
    GroupCallFactory = None
    GroupCallFile = None

logger = logging.getLogger(__name__)


class MusicManager:
    def __init__(self, client):
        self.client = client
        self.data_dir = Path("data")
        self.downloads_dir = self.data_dir / "downloads"
        
        # Ensure directories exist
        self.data_dir.mkdir(exist_ok=True)
        self.downloads_dir.mkdir(exist_ok=True)
        
        # Group calls storage - exactly like VoiceMod
        self.group_calls: Dict[int, any] = {}
        
        # YoutubeDL options - working configuration from VoiceMod
        self.ytdlopts = {
            "format": "bestaudio",
            "addmetadata": True,
            "key": "FFmpegMetadata",
            "writethumbnail": True,
            "prefer_ffmpeg": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ],
            "outtmpl": str(self.downloads_dir / "ytdl_out.mp3"),
            "quiet": True,
            "logtostderr": False,
        }

    def _get_call(self, chat_id: int):
        """Get or create group call for chat - VoiceMod implementation"""
        if not PYTGCALLS_AVAILABLE:
            raise Exception("Voice chat features not available - pytgcalls dependency not installed")
            
        if chat_id not in self.group_calls:
            try:
                self.group_calls[chat_id] = GroupCallFactory(
                    self.client, 
                    GroupCallFactory.MTPROTO_CLIENT_TYPE.TELETHON
                ).get_file_group_call()
                logger.info(f"Created new group call for chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to create group call for {chat_id}: {e}")
                raise
        return self.group_calls[chat_id]

    async def join_voice_chat(self, chat_id: int) -> bool:
        """Join voice chat - VoiceMod style"""
        try:
            self._get_call(chat_id)
            await self.group_calls[chat_id].start(chat_id)
            logger.info(f"✅ Joined voice chat in {chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to join voice chat in {chat_id}: {e}")
            return False

    async def leave_voice_chat(self, chat_id: int) -> bool:
        """Leave voice chat - VoiceMod style"""
        try:
            if chat_id in self.group_calls:
                await self.group_calls[chat_id].stop()
                del self.group_calls[chat_id]
                
                # Clean up audio file
                try:
                    os.remove(f"{chat_id}.raw")
                except FileNotFoundError:
                    pass
                
                logger.info(f"✅ Left voice chat in {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to leave voice chat in {chat_id}: {e}")
            return False

    async def download_audio(self, source: str) -> Optional[str]:
        """Download audio from URL - VoiceMod implementation"""
        try:
            # Clean up previous downloads
            for file in self.downloads_dir.glob("ytdl_out.*"):
                if file.is_file():
                    file.unlink()
            
            with YoutubeDL(self.ytdlopts) as ydl:
                ydl.extract_info(source)
            
            # Return the downloaded file path
            audio_file = self.downloads_dir / "ytdl_out.mp3"
            if audio_file.exists():
                return str(audio_file)
            
            return None
        except Exception as e:
            logger.error(f"❌ Failed to download audio: {e}")
            return None

    async def convert_audio(self, input_file: str, chat_id: int) -> str:
        """Convert audio to required format - exact VoiceMod implementation"""
        output_file = f"{chat_id}.raw"
        
        try:
            # Remove existing output file
            if os.path.exists(output_file):
                os.remove(output_file)
            
            # Convert using ffmpeg - VoiceMod configuration
            ffmpeg.input(input_file).output(
                output_file, 
                format="s16le", 
                acodec="pcm_s16le", 
                ac=2, 
                ar="48k"
            ).overwrite_output().run()
            
            # Clean up input file
            os.remove(input_file)
                
            return output_file
            
        except Exception as e:
            logger.error(f"❌ Failed to convert audio: {e}")
            raise

    async def play_audio(self, chat_id: int, source: str) -> bool:
        """Play audio in voice chat - VoiceMod implementation"""
        try:
            # Check if we're in voice chat
            if chat_id not in self.group_calls:
                logger.error(f"❌ Not joined to voice chat in {chat_id}")
                return False
            
            # Download audio
            logger.info(f"🎵 Downloading audio from: {source}")
            audio_file = await self.download_audio(source)
            if not audio_file:
                logger.error("❌ Failed to download audio")
                return False
            
            # Convert audio to raw format
            logger.info(f"🔄 Converting audio for voice chat")
            raw_file = await self.convert_audio(audio_file, chat_id)
            
            # Play using VoiceMod method
            logger.info(f"▶️ Starting playback in chat {chat_id}")
            self.group_calls[chat_id].input_filename = raw_file
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to play audio: {e}")
            return False

    async def play_from_file(self, chat_id: int, file_path: str) -> bool:
        """Play audio from local file - VoiceMod implementation"""
        try:
            # Check if we're in voice chat
            if chat_id not in self.group_calls:
                logger.error(f"❌ Not joined to voice chat in {chat_id}")
                return False
                
            # Convert audio to raw format
            logger.info(f"🔄 Converting audio file for voice chat")
            raw_file = await self.convert_audio(file_path, chat_id)
            
            # Play using VoiceMod method
            logger.info(f"▶️ Starting playback in chat {chat_id}")
            self.group_calls[chat_id].input_filename = raw_file
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to play audio from file: {e}")
            return False

    async def stop_audio(self, chat_id: int) -> bool:
        """Stop audio playback - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].stop_playout()
                logger.info(f"⏹️ Stopped playback in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to stop audio: {e}")
            return False

    async def pause_audio(self, chat_id: int) -> bool:
        """Pause audio playback - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].pause_playout()
                logger.info(f"⏸️ Paused playback in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to pause audio: {e}")
            return False

    async def resume_audio(self, chat_id: int) -> bool:
        """Resume audio playback - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].resume_playout()
                logger.info(f"▶️ Resumed playback in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to resume audio: {e}")
            return False

    async def replay_audio(self, chat_id: int) -> bool:
        """Replay current audio - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].restart_playout()
                logger.info(f"🔄 Replaying audio in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to replay audio: {e}")
            return False

    async def mute_audio(self, chat_id: int) -> bool:
        """Mute audio - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].set_is_mute(True)
                logger.info(f"🔇 Muted in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to mute audio: {e}")
            return False

    async def unmute_audio(self, chat_id: int) -> bool:
        """Unmute audio - VoiceMod implementation"""
        try:
            if chat_id in self.group_calls:
                self.group_calls[chat_id].set_is_mute(False)
                logger.info(f"🔊 Unmuted in chat {chat_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to unmute audio: {e}")
            return False

    async def shazam_recognize(self, audio_bytes: bytes) -> Optional[dict]:
        """Recognize track using Shazam - Fixed implementation"""
        try:
            shazam = Shazam(audio_bytes)
            recog = shazam.recognizeSong()
            
            # Get the first result from generator
            result = list(recog)
            if result:
                track = result[0][1]["track"]
                
                response = {
                    "title": track.get("title", "Unknown"),
                    "artist": track.get("subtitle", "Unknown"), 
                    "image": track.get("images", {}).get("background", ""),
                    "share": track.get("share", {}).get("subject", "")
                }
                
                logger.info(f"🎵 Recognized track: {response['title']} - {response['artist']}")
                return response
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to recognize track: {e}")
            return None

    def get_status(self, chat_id: int) -> dict:
        """Get playback status"""
        is_connected = chat_id in self.group_calls
        
        return {
            "connected": is_connected,
            "chat_id": chat_id,
            "has_group_call": is_connected
        }

    def debug_info(self) -> str:
        """Debug information - VoiceMod style"""
        return f"DEBUG: Group calls: {list(self.group_calls.keys())}"