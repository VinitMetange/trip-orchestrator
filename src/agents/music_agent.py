"""
TripOrchestrator - Music Agent
Handles Spotify integration, collaborative queues, mood-based playlists
"""
import os
from typing import Dict, List, Optional
from src.integrations.spotify import SpotifyClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Context-based playlist rules
CONTEXT_RULES = {
    "highway": {"genres": ["bollywood", "pop", "upbeat"], "energy": "high"},
    "scenic": {"genres": ["ambient", "instrumental", "soft"], "energy": "low"},
    "traffic": {"genres": ["podcasts", "calm", "easy-listening"], "energy": "low"},
    "night": {"genres": ["lo-fi", "soft-rock", "jazz"], "energy": "low"},
    "party": {"genres": ["dance", "edm", "party"], "energy": "very_high"},
    "morning": {"genres": ["upbeat", "pop", "bhangra"], "energy": "medium"}
}

VOTING_THRESHOLD = 0.8  # 80% of group must approve

class MusicAgent:
    def __init__(self, llm):
        self.llm = llm
        self.spotify = SpotifyClient()

    async def run(self, state: dict) -> dict:
        """Process music-related messages"""
        messages = state["messages"]
        trip_state = state.get("trip_state", {})
        last_message = messages[-1].content.lower() if messages else ""

        # Check if Spotify is linked
        if not trip_state.get("spotify_token"):
            return {
                **state,
                "response": self._get_spotify_link_prompt()
            }

        # Parse intent
        if any(word in last_message for word in ["play", "queue", "song", "music"]):
            return await self._handle_play_request(state, trip_state, messages[-1].content)
        elif "vote" in last_message or "skip" in last_message:
            return await self._handle_vote(state, trip_state, last_message)
        elif "pause" in last_message or "stop" in last_message:
            return await self._handle_pause(state, trip_state)
        elif "volume" in last_message:
            return await self._handle_volume(state, trip_state, last_message)
        else:
            # Context-aware suggestion
            return await self._suggest_contextual_music(state, trip_state)

    async def _handle_play_request(self, state: dict, trip_state: dict, message: str) -> dict:
        """Queue a song/playlist based on request"""
        # Detect driving context
        context = self._detect_context(trip_state)
        
        # Search Spotify
        search_results = await self.spotify.search(
            query=self._extract_search_query(message),
            search_type="track",
            limit=3
        )

        if not search_results:
            return {
                **state,
                "response": "🎵 Song not found on Spotify. Try another? Or share Spotify link directly!"
            }

        top_result = search_results[0]
        track_name = top_result.get("name")
        artist = top_result.get("artists", [{}])[0].get("name")
        uri = top_result.get("uri")

        # Queue on driver's device
        driver_device = trip_state.get("driver_device_id")
        if driver_device:
            await self.spotify.queue_track(
                track_uri=uri,
                access_token=trip_state["spotify_token"],
                device_id=driver_device
            )
            response = f"🎵 Queued *{track_name}* by {artist}\nGroup vote? 👍 Yes / 👎 Skip"
        else:
            response = f"🎵 Driver: Link your Spotify with *spotify_auth* to enable playback.\nMeanwhile, here's the track: {top_result.get('external_url', '')}"

        return {
            **state,
            "response": response,
            "trip_state": {
                **trip_state,
                "current_track": {"name": track_name, "artist": artist, "uri": uri},
                "pending_votes": {uri: {"track": track_name, "votes": {}}}
            }
        }

    async def _handle_vote(self, state: dict, trip_state: dict, message: str) -> dict:
        """Handle music voting"""
        members = trip_state.get("members", [])
        pending_votes = trip_state.get("pending_votes", {})
        
        if not pending_votes:
            return {**state, "response": "🎵 No pending votes. Request a song first!"}

        # Get most recent vote item
        vote_uri = list(pending_votes.keys())[-1]
        vote_data = pending_votes[vote_uri]
        
        # Determine if skip or yes vote
        is_yes = any(w in message for w in ["yes", "approve", "👍", "play"])
        is_no = any(w in message for w in ["skip", "no", "👎", "stop"])
        
        # Add vote (simplified - in production, track per user)
        votes = vote_data.get("votes", {})
        sender = state["messages"][-1].content.split("]")[0].lstrip("[")
        votes[sender] = "yes" if is_yes else "no"
        
        yes_count = sum(1 for v in votes.values() if v == "yes")
        vote_ratio = yes_count / max(len(members), 1)
        
        if vote_ratio >= VOTING_THRESHOLD:
            return {
                **state,
                "response": f"🎉 {int(vote_ratio*100)}% voted yes! Playing *{vote_data['track']}* now!"
            }
        elif (len(votes) == len(members)):
            return {
                **state,
                "response": f"👎 Majority voted to skip. Skipping *{vote_data['track']}*."
            }
        else:
            remaining = len(members) - len(votes)
            return {
                **state,
                "response": f"📊 Votes: {yes_count} Yes, {len(votes)-yes_count} No. {remaining} haven't voted yet."
            }

    async def _handle_pause(self, state: dict, trip_state: dict) -> dict:
        """Pause/stop playback"""
        if trip_state.get("spotify_token") and trip_state.get("driver_device_id"):
            await self.spotify.pause(trip_state["spotify_token"], trip_state["driver_device_id"])
        return {**state, "response": "⏸️ Music paused. Resume with *play*"}

    async def _handle_volume(self, state: dict, trip_state: dict, message: str) -> dict:
        """Adjust volume"""
        import re
        vol_match = re.search(r'(\d+)', message)
        volume = int(vol_match.group(1)) if vol_match else (50 if "down" in message else 70)
        volume = max(0, min(100, volume))
        
        if trip_state.get("spotify_token") and trip_state.get("driver_device_id"):
            await self.spotify.set_volume(volume, trip_state["spotify_token"], trip_state["driver_device_id"])
        return {**state, "response": f"🔊 Volume set to {volume}%"}

    async def _suggest_contextual_music(self, state: dict, trip_state: dict) -> dict:
        """Suggest music based on trip context"""
        context = self._detect_context(trip_state)
        rules = CONTEXT_RULES.get(context, CONTEXT_RULES["highway"])
        genres = ", ".join(rules["genres"])
        
        response = f"🎵 *Music Suggestion*\n"
        response += f"Context: {context.title()} mode\n"
        response += f"Recommended: {genres}\n"
        response += f"Try: *play Bollywood road trip* or *play chill beats*"
        
        return {**state, "response": response}

    def _detect_context(self, trip_state: dict) -> str:
        """Detect driving context from trip state"""
        speed = trip_state.get("speed_kmh", 0)
        hour = trip_state.get("current_hour", 12)
        road_type = trip_state.get("road_type", "highway")
        
        if hour < 6 or hour > 22:
            return "night"
        if speed < 20:
            return "traffic"
        if speed > 60:
            return "highway"
        if road_type == "scenic":
            return "scenic"
        return "highway"

    def _extract_search_query(self, message: str) -> str:
        """Extract search query from play request"""
        message = message.lower()
        for prefix in ["play ", "queue ", "put on ", "start playing "]:
            if prefix in message:
                return message.split(prefix, 1)[1].strip()
        return message.strip()

    def _get_spotify_link_prompt(self) -> str:
        """Return Spotify linking instructions"""
        spotify_auth_url = f"https://accounts.spotify.com/authorize?client_id={os.getenv('SPOTIFY_CLIENT_ID')}&response_type=code&redirect_uri={os.getenv('SPOTIFY_REDIRECT_URI')}&scope=user-modify-playback-state user-read-playback-state"
        return f"""🎵 *Link Spotify for group music control!*

Driver: Click to authorize:
{spotify_auth_url}

Once linked, everyone can:
- Request songs by voice/text
- Vote on tracks
- Control playback hands-free🎵"
