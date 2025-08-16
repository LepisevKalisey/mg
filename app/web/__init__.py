from __future__ import annotations

"""Web module for MG Digest.

This module provides the web interface for the application.
"""

import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.common.config import load_config
from app.common.logging import setup_logging
from app.admin import router as admin_router
from app.db.digests import DigestRepository

logger = setup_logging()

# Create FastAPI app
app = FastAPI(
    title="MG Digest",
    description="A digest generator for Telegram channels",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, this should be restricted
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include admin router
app.include_router(admin_router)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Public API endpoints
@app.get("/api/digests", tags=["public"])
async def get_public_digests() -> List[Dict]:
    """Get all published digests."""
    digest_repo = DigestRepository()
    digests = await digest_repo.get_digests(published=True)
    return [digest.to_dict() for digest in digests]


@app.get("/api/digests/{digest_id}", tags=["public"])
async def get_public_digest(digest_id: int) -> Dict:
    """Get a published digest by ID."""
    digest_repo = DigestRepository()
    digest = await digest_repo.get_digest(digest_id)
    
    if not digest or not digest.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Digest not found: {digest_id}"
        )
    
    return digest.to_dict()


@app.get("/api/digests/{digest_id}/items", tags=["public"])
async def get_public_digest_items(digest_id: int) -> List[Dict]:
    """Get items for a published digest."""
    digest_repo = DigestRepository()
    digest = await digest_repo.get_digest(digest_id)
    
    if not digest or not digest.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Digest not found: {digest_id}"
        )
    
    items = await digest_repo.get_digest_items(digest_id)
    return [item.to_dict() for item in items]


# Web interface
@app.get("/", response_class=HTMLResponse, tags=["web"])
async def index():
    """Render the index page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MG Digest</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <header>
            <h1>MG Digest</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/digests">Digests</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
        </header>
        <main>
            <section class="hero">
                <h2>Welcome to MG Digest</h2>
                <p>A digest generator for Telegram channels</p>
                <a href="/digests" class="button">View Digests</a>
            </section>
        </main>
        <footer>
            <p>&copy; 2023 MG Digest</p>
        </footer>
        <script src="/static/js/main.js"></script>
    </body>
    </html>
    """


@app.get("/digests", response_class=HTMLResponse, tags=["web"])
async def digests_page():
    """Render the digests page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Digests - MG Digest</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <header>
            <h1>MG Digest</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/digests">Digests</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
        </header>
        <main>
            <section class="digests">
                <h2>Digests</h2>
                <div id="digests-list">
                    <p>Loading digests...</p>
                </div>
            </section>
        </main>
        <footer>
            <p>&copy; 2023 MG Digest</p>
        </footer>
        <script>
            // Fetch digests from API
            fetch('/api/digests')
                .then(response => response.json())
                .then(digests => {
                    const digestsList = document.getElementById('digests-list');
                    digestsList.innerHTML = '';
                    
                    if (digests.length === 0) {
                        digestsList.innerHTML = '<p>No digests available.</p>';
                        return;
                    }
                    
                    digests.forEach(digest => {
                        const digestElement = document.createElement('div');
                        digestElement.className = 'digest';
                        digestElement.innerHTML = `
                            <h3><a href="/digests/${digest.id}">${digest.title}</a></h3>
                            <p>${digest.description}</p>
                            <p class="date">Published: ${new Date(digest.publish_date).toLocaleDateString()}</p>
                        `;
                        digestsList.appendChild(digestElement);
                    });
                })
                .catch(error => {
                    console.error('Error fetching digests:', error);
                    const digestsList = document.getElementById('digests-list');
                    digestsList.innerHTML = '<p>Error loading digests. Please try again later.</p>';
                });
        </script>
        <script src="/static/js/main.js"></script>
    </body>
    </html>
    """


@app.get("/digests/{digest_id}", response_class=HTMLResponse, tags=["web"])
async def digest_page(digest_id: int):
    """Render a digest page."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Digest - MG Digest</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <header>
            <h1>MG Digest</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/digests">Digests</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
        </header>
        <main>
            <section class="digest-detail">
                <div id="digest-content">
                    <p>Loading digest...</p>
                </div>
                <div id="digest-items">
                    <p>Loading items...</p>
                </div>
            </section>
        </main>
        <footer>
            <p>&copy; 2023 MG Digest</p>
        </footer>
        <script>
            // Fetch digest from API
            fetch('/api/digests/{digest_id}')
                .then(response => {{
                    if (!response.ok) {{
                        throw new Error('Digest not found');
                    }}
                    return response.json();
                }})
                .then(digest => {{
                    const digestContent = document.getElementById('digest-content');
                    digestContent.innerHTML = `
                        <h2>${{digest.title}}</h2>
                        <p>${{digest.description}}</p>
                        <p class="date">Published: ${{new Date(digest.publish_date).toLocaleDateString()}}</p>
                    `;
                    
                    // Fetch digest items
                    return fetch('/api/digests/{digest_id}/items');
                }})
                .then(response => response.json())
                .then(items => {{
                    const digestItems = document.getElementById('digest-items');
                    digestItems.innerHTML = '';
                    
                    if (items.length === 0) {{
                        digestItems.innerHTML = '<p>No items in this digest.</p>';
                        return;
                    }}
                    
                    const itemsList = document.createElement('ul');
                    itemsList.className = 'items-list';
                    
                    items.forEach(item => {{
                        const itemElement = document.createElement('li');
                        itemElement.className = 'item';
                        itemElement.innerHTML = `
                            <h3>${{item.title}}</h3>
                            <p>${{item.summary}}</p>
                            <p class="source">Source: ${{item.source_name}}</p>
                            <p class="topic">Topic: ${{item.topic_name}}</p>
                            <p class="date">Date: ${{new Date(item.date).toLocaleDateString()}}</p>
                            <a href="${{item.url}}" target="_blank" class="button">Read Original</a>
                        `;
                        itemsList.appendChild(itemElement);
                    }});
                    
                    digestItems.appendChild(itemsList);
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    const digestContent = document.getElementById('digest-content');
                    digestContent.innerHTML = '<p>Error loading digest. Please try again later.</p>';
                    const digestItems = document.getElementById('digest-items');
                    digestItems.innerHTML = '';
                }});
        </script>
        <script src="/static/js/main.js"></script>
    </body>
    </html>
    """


@app.get("/about", response_class=HTMLResponse, tags=["web"])
async def about_page():
    """Render the about page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>About - MG Digest</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <header>
            <h1>MG Digest</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/digests">Digests</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
        </header>
        <main>
            <section class="about">
                <h2>About MG Digest</h2>
                <p>MG Digest is a digest generator for Telegram channels. It collects messages from various Telegram channels, categorizes them by topic, and generates digests that can be published to various platforms.</p>
                <h3>Features</h3>
                <ul>
                    <li>Collect messages from Telegram channels</li>
                    <li>Categorize messages by topic</li>
                    <li>Generate digests with summaries</li>
                    <li>Publish digests to Telegram, email, and web</li>
                </ul>
            </section>
        </main>
        <footer>
            <p>&copy; 2023 MG Digest</p>
        </footer>
        <script src="/static/js/main.js"></script>
    </body>
    </html>
    """


@app.get("/admin", response_class=HTMLResponse, tags=["web"])
async def admin_page():
    """Render the admin page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin - MG Digest</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/static/css/style.css">
        <link rel="stylesheet" href="/static/css/admin.css">
    </head>
    <body>
        <header>
            <h1>MG Digest Admin</h1>
            <nav>
                <ul>
                    <li><a href="/admin">Dashboard</a></li>
                    <li><a href="/admin/digests">Digests</a></li>
                    <li><a href="/admin/sources">Sources</a></li>
                    <li><a href="/admin/topics">Topics</a></li>
                    <li><a href="/admin/users">Users</a></li>
                    <li><a href="/">Public Site</a></li>
                </ul>
            </nav>
        </header>
        <main>
            <section class="admin-dashboard">
                <h2>Admin Dashboard</h2>
                <div class="dashboard-widgets">
                    <div class="widget">
                        <h3>Digests</h3>
                        <p id="digests-count">Loading...</p>
                    </div>
                    <div class="widget">
                        <h3>Sources</h3>
                        <p id="sources-count">Loading...</p>
                    </div>
                    <div class="widget">
                        <h3>Topics</h3>
                        <p id="topics-count">Loading...</p>
                    </div>
                    <div class="widget">
                        <h3>Users</h3>
                        <p id="users-count">Loading...</p>
                    </div>
                </div>
                <div class="actions">
                    <h3>Quick Actions</h3>
                    <div class="action-buttons">
                        <a href="/admin/digests/new" class="button">Create Digest</a>
                        <a href="/admin/sources/new" class="button">Add Source</a>
                        <a href="/admin/topics/new" class="button">Add Topic</a>
                    </div>
                </div>
            </section>
        </main>
        <footer>
            <p>&copy; 2023 MG Digest</p>
        </footer>
        <script>
            // Fetch counts from API
            fetch('/api/admin/digests')
                .then(response => response.json())
                .then(digests => {
                    document.getElementById('digests-count').textContent = digests.length;
                })
                .catch(error => {
                    console.error('Error fetching digests:', error);
                    document.getElementById('digests-count').textContent = 'Error';
                });
                
            fetch('/api/admin/sources')
                .then(response => response.json())
                .then(sources => {
                    document.getElementById('sources-count').textContent = sources.length;
                })
                .catch(error => {
                    console.error('Error fetching sources:', error);
                    document.getElementById('sources-count').textContent = 'Error';
                });
                
            fetch('/api/admin/topics')
                .then(response => response.json())
                .then(topics => {
                    document.getElementById('topics-count').textContent = topics.length;
                })
                .catch(error => {
                    console.error('Error fetching topics:', error);
                    document.getElementById('topics-count').textContent = 'Error';
                });
                
            fetch('/api/admin/users')
                .then(response => response.json())
                .then(users => {
                    document.getElementById('users-count').textContent = users.length;
                })
                .catch(error => {
                    console.error('Error fetching users:', error);
                    document.getElementById('users-count').textContent = 'Error';
                });
        </script>
        <script src="/static/js/admin.js"></script>
    </body>
    </html>
    """


def main():
    """Run the web server."""
    import uvicorn
    
    config = load_config()
    host = config.get("WEB_HOST", "0.0.0.0")
    port = int(config.get("WEB_PORT", 8000))
    
    uvicorn.run("app.web:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()