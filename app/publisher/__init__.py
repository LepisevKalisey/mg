from __future__ import annotations

"""Publisher module for MG Digest.

This module provides functionality for publishing digests to various channels.
"""

import logging
from typing import Dict, List, Optional

from app.common.config import load_config
from app.common.logging import setup_logging

logger = setup_logging()


class Publisher:
    """Base class for digest publishers."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or load_config()
    
    async def publish(self, digest_id: int) -> bool:
        """Publish a digest.
        
        Args:
            digest_id: The ID of the digest to publish.
            
        Returns:
            True if the digest was published successfully, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement this method")


class TelegramPublisher(Publisher):
    """Publisher for Telegram channels."""
    
    async def publish(self, digest_id: int) -> bool:
        """Publish a digest to a Telegram channel.
        
        Args:
            digest_id: The ID of the digest to publish.
            
        Returns:
            True if the digest was published successfully, False otherwise.
        """
        from app.db.digests import DigestRepository
        
        try:
            # Get the digest
            digest_repo = DigestRepository()
            digest = await digest_repo.get_digest(digest_id)
            
            if not digest:
                logger.error(f"Digest not found: {digest_id}")
                return False
            
            # Check if the digest is published
            if not digest.published:
                logger.error(f"Digest is not published: {digest_id}")
                return False
            
            # Get the Telegram channel ID from config
            channel_id = self.config.get("TELEGRAM_CHANNEL_ID")
            if not channel_id:
                logger.error("Telegram channel ID not configured")
                return False
            
            # Get the Telegram bot token from config
            bot_token = self.config.get("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                logger.error("Telegram bot token not configured")
                return False
            
            # Send the digest to the channel
            # In a real application, you would use the Telegram Bot API to send the message
            # For now, we'll just log the message
            logger.info(f"Publishing digest {digest_id} to Telegram channel {channel_id}")
            
            # Mark the digest as published in the database
            await digest_repo.update_digest(
                digest_id=digest_id,
                published=True
            )
            
            return True
        except Exception as e:
            logger.error(f"Error publishing digest to Telegram: {e}")
            return False


class EmailPublisher(Publisher):
    """Publisher for email newsletters."""
    
    async def publish(self, digest_id: int) -> bool:
        """Publish a digest as an email newsletter.
        
        Args:
            digest_id: The ID of the digest to publish.
            
        Returns:
            True if the digest was published successfully, False otherwise.
        """
        from app.db.digests import DigestRepository
        from app.db.users import UserRepository
        
        try:
            # Get the digest
            digest_repo = DigestRepository()
            digest = await digest_repo.get_digest(digest_id)
            
            if not digest:
                logger.error(f"Digest not found: {digest_id}")
                return False
            
            # Check if the digest is published
            if not digest.published:
                logger.error(f"Digest is not published: {digest_id}")
                return False
            
            # Get the SMTP settings from config
            smtp_host = self.config.get("SMTP_HOST")
            smtp_port = self.config.get("SMTP_PORT")
            smtp_user = self.config.get("SMTP_USER")
            smtp_password = self.config.get("SMTP_PASSWORD")
            
            if not all([smtp_host, smtp_port, smtp_user, smtp_password]):
                logger.error("SMTP settings not configured")
                return False
            
            # Get the subscribers
            user_repo = UserRepository()
            subscribers = await user_repo.get_subscribers()
            
            if not subscribers:
                logger.warning("No subscribers found")
                return True
            
            # Send the digest to the subscribers
            # In a real application, you would use an email library to send the emails
            # For now, we'll just log the message
            logger.info(f"Publishing digest {digest_id} to {len(subscribers)} subscribers")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing digest to email: {e}")
            return False


class WebPublisher(Publisher):
    """Publisher for web interface."""
    
    async def publish(self, digest_id: int) -> bool:
        """Publish a digest to the web interface.
        
        Args:
            digest_id: The ID of the digest to publish.
            
        Returns:
            True if the digest was published successfully, False otherwise.
        """
        from app.db.digests import DigestRepository
        
        try:
            # Get the digest
            digest_repo = DigestRepository()
            digest = await digest_repo.get_digest(digest_id)
            
            if not digest:
                logger.error(f"Digest not found: {digest_id}")
                return False
            
            # Check if the digest is published
            if not digest.published:
                logger.error(f"Digest is not published: {digest_id}")
                return False
            
            # In a real application, you might need to update a cache or trigger a webhook
            # For now, we'll just log the message
            logger.info(f"Publishing digest {digest_id} to web interface")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing digest to web: {e}")
            return False


async def publish_digest(digest_id: int) -> Dict:
    """Publish a digest to all configured channels.
    
    Args:
        digest_id: The ID of the digest to publish.
        
    Returns:
        A dictionary containing the results of the publishing operations.
    """
    config = load_config()
    results = {}
    
    # Get the enabled publishers from config
    enabled_publishers = config.get("publishers", {"telegram": True, "email": True, "web": True})
    
    # Publish to Telegram if enabled
    if enabled_publishers.get("telegram", True):
        telegram_publisher = TelegramPublisher(config)
        results["telegram"] = await telegram_publisher.publish(digest_id)
    
    # Publish to email if enabled
    if enabled_publishers.get("email", True):
        email_publisher = EmailPublisher(config)
        results["email"] = await email_publisher.publish(digest_id)
    
    # Publish to web if enabled
    if enabled_publishers.get("web", True):
        web_publisher = WebPublisher(config)
        results["web"] = await web_publisher.publish(digest_id)
    
    return results