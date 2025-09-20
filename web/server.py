#!/usr/bin/env python3
"""
Web Interface for Telegram Music Userbot
"""

import asyncio
import json
import logging
import os
import secrets
import hashlib
from pathlib import Path
from typing import Optional

from aiohttp import web, WSMsgType
from aiohttp_jinja2 import setup as jinja_setup, template
import jinja2
import aiofiles

logger = logging.getLogger(__name__)


class WebServer:
    def __init__(self, userbot, port: int = 5000):
        self.userbot = userbot
        self.port = port
        self.app = None
        self.runner = None
        self.site = None
        
        # Security
        self.auth_secret = os.environ.get('AUTH_SECRET') or self._generate_auth_secret()
        logger.info("🔐 Web authentication enabled")
        logger.info("🔑 AUTH_SECRET для доступа сгенерирован")
        
        # Paths
        self.templates_dir = Path(__file__).parent.parent / "templates"
        self.static_dir = Path(__file__).parent.parent / "static"

    async def start(self):
        """Start web server"""
        self.app = web.Application()
        
        # Setup Jinja2
        jinja_setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(self.templates_dir))
        )
        
        # Add security headers middleware
        self.app.middlewares.append(self._security_headers_middleware)
        
        # Setup routes
        self._setup_routes()
        
        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        
        logger.info(f"🌐 Web server started on http://0.0.0.0:{self.port}")
        logger.info("🔑 Для доступа используйте Bearer токен (проверьте переменную AUTH_SECRET)")
        logger.info("📋 Добавьте заголовок: Authorization: Bearer <токен>")

    async def run_forever(self):
        """Start server and keep it running"""
        await self.start()
        
        # Keep running forever until cancelled
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour at a time
        except asyncio.CancelledError:
            logger.info("Web server shutting down...")
            raise

    def _generate_auth_secret(self) -> str:
        """Generate a random auth secret"""
        secret = secrets.token_urlsafe(16)
        logger.info("🔧 Сгенерирован новый AUTH_SECRET")
        # Don't log the actual secret for security
        logger.info("🔐 AUTH_SECRET generated for API access")
        logger.info("📋 Check AUTH_SECRET environment variable or server logs for access token")
        print(f"🔐 AUTH_SECRET for web access: {secret}")  # Print to console only
        return secret
    
    @web.middleware
    async def _security_headers_middleware(self, request, handler):
        """Add security headers to all responses"""
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        
        # Add security headers  
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Allow iframe for Replit proxy
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        if response.status == 401:
            response.headers['Cache-Control'] = 'no-store'
        
        return response
    
    def _check_auth(self, request) -> bool:
        """Check if request is authenticated"""
        # Only check Authorization header - no query parameters
        auth_header = request.headers.get('Authorization')
        if auth_header == f"Bearer {self.auth_secret}":
            return True
            
        return False
    
    def _require_auth(self, handler):
        """Decorator to require authentication"""
        async def wrapper(request):
            if not self._check_auth(request):
                return web.json_response({
                    'success': False,
                    'error': 'Authentication required. Provide secret in Authorization header.'
                }, status=401)
            return await handler(request)
        return wrapper

    async def stop(self):
        """Stop web server"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    def _setup_routes(self):
        """Setup web routes"""
        
        # Static files
        self.app.router.add_static('/static/', path=self.static_dir, name='static')
        
        # Main routes
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/app', self.app_page)
        self.app.router.add_get('/healthz', self.healthcheck)
        self.app.router.add_get('/api/user_status', self._require_auth(self.api_get_user_status))
        
        # API routes (protected)
        self.app.router.add_post('/api/init', self._require_auth(self.api_init))
        self.app.router.add_post('/api/send_code', self._require_auth(self.api_send_code))
        self.app.router.add_post('/api/verify_code', self._require_auth(self.api_verify_code))
        self.app.router.add_get('/api/status', self._require_auth(self.api_status))
        self.app.router.add_post('/api/logout', self._require_auth(self.api_logout))

    @template('login.html')
    async def index(self, request):
        """Main page - public login form"""
        # Public page - no auth required
        return {
            'title': 'Telegram Music Userbot - Login',
            'version': self.userbot.version
        }

    @template('index.html')
    async def app_page(self, request):
        """App page - public shell with API auth"""
        return {
            'title': 'Telegram Music Userbot',
            'version': self.userbot.version
        }

    async def healthcheck(self, request):
        """Health check endpoint - no auth required"""
        return web.json_response({
            'status': 'healthy',
            'version': self.userbot.version,
            'port': self.port
        })

    async def api_get_user_status(self, request):
        """Get user status via API"""
        user_info = None
        if self.userbot.me:
            user_info = {
                'id': self.userbot.me.id,
                'first_name': self.userbot.me.first_name,
                'last_name': getattr(self.userbot.me, 'last_name', None),
                'username': getattr(self.userbot.me, 'username', None),
                'phone': getattr(self.userbot.me, 'phone', None)
            }
        
        return web.json_response({
            'success': True,
            'authenticated': self.userbot.is_authenticated,
            'user': user_info,
            'status': self.userbot.get_status()
        })

    async def api_init(self, request):
        """Initialize userbot with API credentials"""
        try:
            data = await request.json()
            api_id = data.get('api_id')
            api_hash = data.get('api_hash')
            
            if not api_id or not api_hash:
                return web.json_response({
                    'success': False,
                    'error': 'API ID and API Hash are required'
                })
            
            await self.userbot.initialize(int(api_id), api_hash)
            
            return web.json_response({
                'success': True,
                'message': 'Userbot initialized successfully'
            })
            
        except ValueError as e:
            return web.json_response({
                'success': False,
                'error': 'API ID must be a valid number'
            })
        except Exception as e:
            logger.error(f"Init error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    async def api_send_code(self, request):
        """Send verification code to phone"""
        try:
            data = await request.json()
            phone = data.get('phone', '').strip()
            
            if not phone:
                return web.json_response({
                    'success': False,
                    'error': 'Phone number is required'
                })
            
            # Ensure client is connected
            if self.userbot.client and not self.userbot.client.is_connected():
                await self.userbot.client.connect()
            
            result = await self.userbot.send_code(phone)
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Send code error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    async def api_verify_code(self, request):
        """Verify phone code and optionally 2FA password"""
        try:
            data = await request.json()
            code = data.get('code', '').strip()
            password = data.get('password', '').strip() or None
            
            if not code:
                return web.json_response({
                    'success': False,
                    'error': 'Verification code is required'
                })
            
            # Ensure client is connected
            if self.userbot.client and not self.userbot.client.is_connected():
                await self.userbot.client.connect()
            
            result = await self.userbot.verify_code(code, password)
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Verify code error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    async def api_status(self, request):
        """Get userbot status"""
        try:
            return web.json_response({
                'success': True,
                'status': self.userbot.get_status()
            })
        except Exception as e:
            logger.error(f"Status error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })

    async def api_logout(self, request):
        """Logout and clear session"""
        try:
            await self.userbot.disconnect()
            
            # Remove session file
            if self.userbot.session_file.exists():
                self.userbot.session_file.unlink()
            
            self.userbot.is_authenticated = False
            self.userbot.me = None
            
            return web.json_response({
                'success': True,
                'message': 'Logged out successfully'
            })
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            })