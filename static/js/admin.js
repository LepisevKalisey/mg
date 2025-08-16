/**
 * Admin JavaScript file for MG Digest
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize admin components
    initializeAdminForms();
    initializeDataTables();
    initializeDeleteConfirmation();
});

/**
 * Initialize admin forms
 */
function initializeAdminForms() {
    // Find all admin forms
    const forms = document.querySelectorAll('.admin-form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            // Prevent default form submission
            event.preventDefault();
            
            // Get form data
            const formData = new FormData(form);
            const jsonData = {};
            
            for (const [key, value] of formData.entries()) {
                // Handle arrays (like topics[] or sources[])
                if (key.endsWith('[]')) {
                    const cleanKey = key.substring(0, key.length - 2);
                    if (!jsonData[cleanKey]) {
                        jsonData[cleanKey] = [];
                    }
                    jsonData[cleanKey].push(value);
                } else {
                    jsonData[key] = value;
                }
            }
            
            // Get form action and method
            const action = form.getAttribute('action');
            const method = form.getAttribute('method') || 'POST';
            
            // Submit form data
            fetch(action, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(jsonData)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Form submission failed');
                }
                return response.json();
            })
            .then(data => {
                // Show success message
                showNotification('Operation completed successfully', 'success');
                
                // Redirect if specified
                const redirect = form.getAttribute('data-redirect');
                if (redirect) {
                    window.location.href = redirect;
                }
            })
            .catch(error => {
                console.error('Form submission error:', error);
                showNotification('An error occurred. Please try again.', 'error');
            });
        });
    });
}

/**
 * Initialize data tables
 */
function initializeDataTables() {
    // Find all admin tables
    const tables = document.querySelectorAll('.admin-table');
    
    tables.forEach(table => {
        // Add sorting functionality if needed
        const headers = table.querySelectorAll('th[data-sort]');
        
        headers.forEach(header => {
            header.addEventListener('click', function() {
                const sortKey = header.getAttribute('data-sort');
                const sortDirection = header.getAttribute('data-direction') || 'asc';
                
                // Toggle sort direction
                const newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
                header.setAttribute('data-direction', newDirection);
                
                // Sort table rows
                sortTable(table, sortKey, newDirection);
            });
        });
    });
}

/**
 * Sort table by column
 * @param {HTMLElement} table - Table element
 * @param {string} sortKey - Column to sort by
 * @param {string} direction - Sort direction (asc or desc)
 */
function sortTable(table, sortKey, direction) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    // Sort rows
    rows.sort((a, b) => {
        const aValue = a.querySelector(`td[data-${sortKey}]`).getAttribute(`data-${sortKey}`);
        const bValue = b.querySelector(`td[data-${sortKey}]`).getAttribute(`data-${sortKey}`);
        
        if (direction === 'asc') {
            return aValue.localeCompare(bValue);
        } else {
            return bValue.localeCompare(aValue);
        }
    });
    
    // Clear table
    while (tbody.firstChild) {
        tbody.removeChild(tbody.firstChild);
    }
    
    // Add sorted rows
    rows.forEach(row => {
        tbody.appendChild(row);
    });
}

/**
 * Initialize delete confirmation
 */
function initializeDeleteConfirmation() {
    // Find all delete buttons
    const deleteButtons = document.querySelectorAll('.delete-button');
    
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(event) {
            // Prevent default action
            event.preventDefault();
            
            // Get confirmation message
            const message = button.getAttribute('data-confirm') || 'Are you sure you want to delete this item?';
            
            // Show confirmation dialog
            if (confirm(message)) {
                // Get delete URL
                const url = button.getAttribute('href');
                
                // Send delete request
                fetch(url, {
                    method: 'DELETE'
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Delete operation failed');
                    }
                    return response.json();
                })
                .then(data => {
                    // Show success message
                    showNotification('Item deleted successfully', 'success');
                    
                    // Remove item from DOM
                    const item = button.closest('.item') || button.closest('tr');
                    if (item) {
                        item.remove();
                    } else {
                        // Reload page if item not found
                        window.location.reload();
                    }
                })
                .catch(error => {
                    console.error('Delete error:', error);
                    showNotification('An error occurred during deletion', 'error');
                });
            }
        });
    });
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