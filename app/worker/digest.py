from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, List, Optional

from app.db.digests import DigestRepository
from app.db.settings import SettingsRepository
from app.db.sources import SourceRepository
from app.db.summaries import SummaryRepository
from app.db.topics import TopicRepository

logger = logging.getLogger(__name__)


async def generate_digest(date: Optional[datetime.date] = None) -> Dict:
    """Generate a digest for the specified date or today.
    
    Args:
        date: The date to generate the digest for. If None, today's date is used.
        
    Returns:
        A dictionary containing the generated digest.
    """
    if date is None:
        date = datetime.date.today()
    
    logger.info(f"Generating digest for {date}")
    
    # Get settings
    settings_repo = SettingsRepository()
    settings = await settings_repo.get_settings()
    
    # Get active sources
    source_repo = SourceRepository()
    sources = await source_repo.get_active_sources()
    
    # Get active topics
    topic_repo = TopicRepository()
    topics = await topic_repo.get_active_topics()
    
    # Get summaries for the date
    summary_repo = SummaryRepository()
    start_date = datetime.datetime.combine(date, datetime.time.min)
    end_date = datetime.datetime.combine(date, datetime.time.max)
    summaries = await summary_repo.get_summaries_by_date_range(start_date, end_date)
    
    # Group summaries by topic
    summaries_by_topic: Dict[int, List] = {}
    for summary in summaries:
        if summary.topic_id not in summaries_by_topic:
            summaries_by_topic[summary.topic_id] = []
        summaries_by_topic[summary.topic_id].append(summary)
    
    # Generate digest content
    content = f"# Daily Digest for {date.strftime('%Y-%m-%d')}\n\n"
    
    for topic in topics:
        topic_summaries = summaries_by_topic.get(topic.id, [])
        if not topic_summaries:
            continue
        
        content += f"## {topic.name}\n\n"
        
        for summary in topic_summaries:
            source = next((s for s in sources if s.id == summary.source_id), None)
            source_name = source.name if source else "Unknown Source"
            
            content += f"### {summary.title}\n\n"
            content += f"{summary.content}\n\n"
            content += f"Source: {source_name}\n\n"
    
    # Create digest
    digest_repo = DigestRepository()
    digest = await digest_repo.create_digest(
        title=f"Daily Digest - {date.strftime('%Y-%m-%d')}",
        description=f"Daily digest for {date.strftime('%B %d, %Y')}",
        content=content,
        published=settings.get("auto_publish_digest", False),
        publish_date=datetime.datetime.now() if settings.get("auto_publish_digest", False) else None
    )
    
    logger.info(f"Digest generated successfully: {digest.id}")
    
    return {
        "id": digest.id,
        "title": digest.title,
        "description": digest.description,
        "published": digest.published,
        "publish_date": digest.publish_date
    }


async def publish_digest(digest_id: int) -> Dict:
    """Publish a digest.
    
    Args:
        digest_id: The ID of the digest to publish.
        
    Returns:
        A dictionary containing the published digest and publishing results.
    """
    logger.info(f"Publishing digest: {digest_id}")
    
    # Get digest
    digest_repo = DigestRepository()
    digest = await digest_repo.get_digest(digest_id)
    
    if not digest:
        logger.error(f"Digest not found: {digest_id}")
        raise ValueError(f"Digest not found: {digest_id}")
    
    # Update digest status
    digest = await digest_repo.update_digest(
        digest_id=digest_id,
        published=True,
        publish_date=datetime.datetime.now()
    )
    
    # Publish to all configured channels
    from app.publisher import publish_digest as publish_to_channels
    publishing_results = await publish_to_channels(digest_id)
    
    logger.info(f"Digest published successfully: {digest_id}")
    
    return {
        "id": digest.id,
        "title": digest.title,
        "description": digest.description,
        "published": digest.published,
        "publish_date": digest.publish_date,
        "publishing_results": publishing_results
    }