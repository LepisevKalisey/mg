from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, List, Optional, Tuple

from telethon.tl.types import Message

from app.db.sources import SourceRepository
from app.db.summaries import SummaryRepository
from app.db.topics import TopicRepository

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Process messages from Telegram channels."""
    
    def __init__(self):
        self.source_repo = SourceRepository()
        self.summary_repo = SummaryRepository()
        self.topic_repo = TopicRepository()
        self.sources_cache: Dict[int, Dict] = {}
        self.topics_cache: List[Dict] = []
        self._cache_initialized = False
    
    async def _initialize_cache(self) -> None:
        """Initialize cache with sources and topics."""
        if self._cache_initialized:
            return
        
        # Get sources
        sources = await self.source_repo.get_active_sources()
        for source in sources:
            self.sources_cache[source.id] = {
                "id": source.id,
                "name": source.name,
                "url": source.url,
                "type": source.type
            }
        
        # Get topics
        topics = await self.topic_repo.get_active_topics()
        self.topics_cache = [
            {
                "id": topic.id,
                "name": topic.name,
                "description": topic.description
            }
            for topic in topics
        ]
        
        self._cache_initialized = True
    
    async def process_message(self, message: Message, channel_id: int) -> Optional[Dict]:
        """Process a message from a Telegram channel.
        
        Args:
            message: The Telegram message.
            channel_id: The ID of the channel the message came from.
            
        Returns:
            A dictionary containing the created summary, or None if the message was not processed.
        """
        await self._initialize_cache()
        
        # Find source by channel ID
        source = None
        for s in self.sources_cache.values():
            if s["url"].endswith(str(channel_id)):
                source = s
                break
        
        if not source:
            logger.warning(f"Source not found for channel ID: {channel_id}")
            return None
        
        # Extract text from message
        if not message.text:
            logger.debug(f"Message has no text: {message.id}")
            return None
        
        # Determine topic (simplified version - in a real app, this would use NLP)
        # For now, just assign to the first topic
        topic = self.topics_cache[0] if self.topics_cache else None
        if not topic:
            logger.warning("No topics available")
            return None
        
        # Create summary
        title = message.text.split("\n")[0][:100]  # First line, truncated to 100 chars
        content = message.text
        
        summary = await self.summary_repo.create_summary(
            title=title,
            content=content,
            source_id=source["id"],
            topic_id=topic["id"]
        )
        
        logger.info(f"Created summary: {summary.id} from message: {message.id}")
        
        return {
            "id": summary.id,
            "title": summary.title,
            "content": summary.content,
            "source_id": summary.source_id,
            "topic_id": summary.topic_id
        }
    
    async def process_messages(self, messages: List[Tuple[Message, int]]) -> List[Dict]:
        """Process multiple messages from Telegram channels.
        
        Args:
            messages: A list of tuples containing the message and channel ID.
            
        Returns:
            A list of dictionaries containing the created summaries.
        """
        results = []
        for message, channel_id in messages:
            result = await self.process_message(message, channel_id)
            if result:
                results.append(result)
        return results