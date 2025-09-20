#!/usr/bin/env python3
"""
Simple database for userbot settings
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.db_file = self.data_dir / "settings.json"
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load data from file"""
        try:
            if self.db_file.exists():
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading database: {e}")
        
        return {}

    def _save(self):
        """Save data to file"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving database: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set value by key"""
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        """Delete key"""
        if key in self._data:
            del self._data[key]
            self._save()

    def clear(self):
        """Clear all data"""
        self._data = {}
        self._save()

    # Async methods for compatibility
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get setting value (async wrapper)"""
        return self.get(key, default)

    async def set_setting(self, key: str, value: Any):
        """Set setting value (async wrapper)"""
        self.set(key, value)
    
    def save_credentials(self, api_id: int, api_hash: str):
        """Save API credentials"""
        self.set('api_id', api_id)
        self.set('api_hash', api_hash)
        logger.info('API credentials saved')
    
    def get_credentials(self) -> Optional[Dict[str, Any]]:
        """Get saved API credentials"""
        api_id = self.get('api_id')
        api_hash = self.get('api_hash')
        if api_id and api_hash:
            return {'api_id': api_id, 'api_hash': api_hash}
        return None