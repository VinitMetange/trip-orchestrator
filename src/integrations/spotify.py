"""
TripOrchestrator - Spotify Web API Integration
Handles music search, queue management, playback control, OAuth
"""
import os
import httpx
import base64
from typing import Dict, List, Optional
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_AUTH_BASE = "https://accounts.spotify.com"

class SpotifyClient:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    def get_auth_url(self) -> str:
        """Generate OAuth authorization URL for driver"""
        scopes = " ".join([
            "user-modify-playback-state",
            "user-read-playback-state",
            "user-read-currently-playing",
            "streaming"
        ])
        return (
            f"{SPOTIFY_AUTH_BASE}/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scopes}"
        )

    async def exchange_code(self, code: str) -> Dict:
        """Exchange authorization code for access token"""
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_AUTH_BASE}/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri
                },
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh access token"""
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_AUTH_BASE}/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                },
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()
            return response.json()

    async def search(self, query: str, search_type: str = "track", limit: int = 5) -> List[Dict]:
        """Search for tracks/playlists on Spotify"""
        # Use client credentials for search (no user auth needed)
        client_token = await self._get_client_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SPOTIFY_API_BASE}/search",
                params={"q": query, "type": search_type, "limit": limit, "market": "IN"},
                headers={"Authorization": f"Bearer {client_token}"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get(f"{search_type}s", {}).get("items", [])

    async def queue_track(self, track_uri: str, access_token: str, device_id: str) -> bool:
        """Add track to playback queue"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_API_BASE}/me/player/queue",
                params={"uri": track_uri, "device_id": device_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 204

    async def get_current_track(self, access_token: str) -> Optional[Dict]:
        """Get currently playing track"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SPOTIFY_API_BASE}/me/player/currently-playing",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 200:
                data = response.json()
                if data and data.get("item"):
                    return {
                        "name": data["item"]["name"],
                        "artist": data["item"]["artists"][0]["name"],
                        "uri": data["item"]["uri"],
                        "progress_ms": data.get("progress_ms", 0),
                        "is_playing": data.get("is_playing", False)
                    }
        return None

    async def pause(self, access_token: str, device_id: str) -> bool:
        """Pause playback"""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{SPOTIFY_API_BASE}/me/player/pause",
                params={"device_id": device_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code in [200, 204]

    async def resume(self, access_token: str, device_id: str) -> bool:
        """Resume playback"""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{SPOTIFY_API_BASE}/me/player/play",
                params={"device_id": device_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code in [200, 204]

    async def skip_next(self, access_token: str, device_id: str) -> bool:
        """Skip to next track"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_API_BASE}/me/player/next",
                params={"device_id": device_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 204

    async def set_volume(self, volume_percent: int, access_token: str, device_id: str) -> bool:
        """Set playback volume (0-100)"""
        volume = max(0, min(100, volume_percent))
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{SPOTIFY_API_BASE}/me/player/volume",
                params={"volume_percent": volume, "device_id": device_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code in [200, 204]

    async def get_available_devices(self, access_token: str) -> List[Dict]:
        """Get user's available Spotify devices"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SPOTIFY_API_BASE}/me/player/devices",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 200:
                return response.json().get("devices", [])
        return []

    async def create_playlist(
        self,
        user_id: str,
        name: str,
        access_token: str,
        description: str = ""
    ) -> Optional[Dict]:
        """Create a trip playlist"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_API_BASE}/users/{user_id}/playlists",
                json={
                    "name": name,
                    "description": description,
                    "public": False
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 201:
                return response.json()
        return None

    async def _get_client_token(self) -> str:
        """Get app-level client credentials token for search"""
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPOTIFY_AUTH_BASE}/api/token",
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()
            return response.json()["access_token"]
