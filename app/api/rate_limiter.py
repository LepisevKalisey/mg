from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, Tuple


class RateLimiter:
    """Simple in-memory rate limiter for API requests.
    
    Limits requests based on client IP address using a sliding window algorithm.
    """
    
    def __init__(self, requests: int = 100, window: int = 60):
        """Initialize the rate limiter.
        
        Args:
            requests: Maximum number of requests allowed in the window.
            window: Time window in seconds.
        """
        self.max_requests = requests
        self.window = window
        self.clients: Dict[str, list] = defaultdict(list)
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if the client is allowed to make a request.
        
        Args:
            client_ip: The client's IP address.
            
        Returns:
            True if the request is allowed, False otherwise.
        """
        now = time.time()
        
        # Remove expired timestamps
        self.clients[client_ip] = [ts for ts in self.clients[client_ip] if now - ts < self.window]
        
        # Check if the client has exceeded the limit
        if len(self.clients[client_ip]) >= self.max_requests:
            return False
        
        # Add the current timestamp
        self.clients[client_ip].append(now)
        return True