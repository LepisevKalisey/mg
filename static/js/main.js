/**
 * Main JavaScript file for MG Digest
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize any components that need JavaScript
    initializeNavigation();
});

/**
 * Initialize responsive navigation
 */
function initializeNavigation() {
    // Add mobile navigation toggle if needed in the future
    // For now, the navigation is simple enough to work with CSS only
}

/**
 * Format date string
 * @param {string} dateString - ISO date string
 * @returns {string} - Formatted date string
 */
function formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

/**
 * Truncate text to a specified length
 * @param {string} text - Text to truncate
 * @param {number} length - Maximum length
 * @returns {string} - Truncated text
 */
function truncateText(text, length = 100) {
    if (!text) return '';
    if (text.length <= length) return text;
    
    return text.substring(0, length) + '...';
}

/**
 * Show notification
 * @param {string} message - Notification message
 * @param {string} type - Notification type (success, error, info)
 */
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add to document
    document.body.appendChild(notification);
    
    // Show notification
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // Hide and remove notification after 5 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 5000);
}

/**
 * Handle API errors
 * @param {Error} error - Error object
 */
function handleApiError(error) {
    console.error('API Error:', error);
    showNotification('An error occurred. Please try again later.', 'error');
}