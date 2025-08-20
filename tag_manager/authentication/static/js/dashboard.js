/**
 * Helix Tag Manager - Admin Dashboard JavaScript
 * Dashboard-specific functionality and interactions
 */

const AdminDashboard = {
    // Initialize dashboard functionality
    init() {
        console.log('🎛️ Initializing Admin Dashboard...');
        this.initSearch();
        this.initAnimations();
        this.initEventListeners();
        
        // Show initialization success
        setTimeout(() => {
            this.showAlert('Dashboard loaded! Press Ctrl+K to search, Ctrl+N for new user', 'success', 3000);
        }, 1000);
        
        console.log('✅ Admin Dashboard initialized successfully');
    },

    // Initialize search functionality
    initSearch() {
        const searchInput = document.getElementById('userSearch');
        const tableRows = document.querySelectorAll('.custom-table tbody tr');
        
        console.log('🔍 Initializing search...');
        console.log('Search input found:', !!searchInput);
        console.log('Table rows found:', tableRows.length);
        
        if (searchInput) {
            // Clear any existing event listeners
            searchInput.removeEventListener('input', this.searchHandler);
            
            // Create bound search handler
            this.searchHandler = this.performSearch.bind(this);
            
            // Add the event listener
            searchInput.addEventListener('input', this.searchHandler);
            
            console.log('✅ Search event listener attached');
        } else {
            console.warn('❌ Search input not found');
        }
    },

    // Perform search functionality
    performSearch(event) {
        const searchInput = event.target;
        const searchTerm = (searchInput.value || '').toLowerCase().trim();
        const tableRows = document.querySelectorAll('.custom-table tbody tr');
        
        console.log('🔍 Performing search for:', searchTerm);
        console.log('Searching in', tableRows.length, 'rows');
        
        let visibleCount = 0;
        
        tableRows.forEach((row, index) => {
            const userDetailsDiv = row.querySelector('.user-details');
            if (!userDetailsDiv) {
                console.warn(`Row ${index} missing .user-details`);
                return;
            }
            
            const userNameElem = userDetailsDiv.querySelector('h6');
            const userEmailElem = userDetailsDiv.querySelector('p');
            
            const userName = userNameElem ? userNameElem.textContent.toLowerCase() : '';
            const userEmail = userEmailElem ? userEmailElem.textContent.toLowerCase() : '';
            
            console.log(`Row ${index}:`, { userName, userEmail });
            
            const matches = searchTerm === '' || 
                          userName.includes(searchTerm) || 
                          userEmail.includes(searchTerm);
            
            if (matches) {
                row.style.display = '';
                row.style.opacity = '1';
                visibleCount++;
            } else {
                row.style.display = 'none';
                row.style.opacity = '0.5';
            }
        });
        
        console.log(`✅ Search complete: ${visibleCount}/${tableRows.length} rows visible`);
        
        // Update search results
        this.updateSearchResults(visibleCount, tableRows.length, searchTerm);
    },

    // Update search results display
    updateSearchResults(visibleCount, totalCount, searchTerm = '') {
        console.log(`📊 Search results: ${visibleCount}/${totalCount} users found`);
        
        // Update search input styling based on results
        const searchInput = document.getElementById('userSearch');
        if (searchInput && searchTerm) {
            if (visibleCount === 0) {
                searchInput.style.borderColor = '#dc3545'; // Red for no results
                searchInput.style.backgroundColor = '#fff5f5';
            } else {
                searchInput.style.borderColor = '#198754'; // Green for results found
                searchInput.style.backgroundColor = '#f0fff4';
            }
        } else if (searchInput) {
            // Reset styling when search is empty
            searchInput.style.borderColor = '';
            searchInput.style.backgroundColor = '';
        }
        
        // Show/hide no results message
        if (visibleCount === 0 && totalCount > 0 && searchTerm) {
            this.showNoResultsMessage(searchTerm);
        } else {
            this.hideNoResultsMessage();
        }
        
        // Update search status in placeholder or add a counter
        if (searchInput && searchTerm) {
            const resultText = visibleCount === 0 ? 'No users found' : `${visibleCount} user${visibleCount !== 1 ? 's' : ''} found`;
            console.log(`🔍 ${resultText} for "${searchTerm}"`);
        }
    },

    // Show no results message
    showNoResultsMessage(searchTerm = '') {
        const existingMessage = document.querySelector('.no-results-message');
        if (existingMessage) return;

        const tableBody = document.querySelector('.custom-table tbody');
        if (tableBody) {
            const message = document.createElement('tr');
            message.className = 'no-results-message';
            message.innerHTML = `
                <td colspan="5" class="text-center py-4">
                    <i class="fas fa-search text-muted mb-2" style="font-size: 24px;"></i>
                    <p class="text-muted mb-0">No users found${searchTerm ? ` for "${searchTerm}"` : ''}</p>
                    <small class="text-muted">Try a different search term or clear the search</small>
                </td>
            `;
            tableBody.appendChild(message);
        }
    },

    // Hide no results message
    hideNoResultsMessage() {
        const message = document.querySelector('.no-results-message');
        if (message) {
            message.remove();
        }
    },

    // Initialize animations and hover effects
    initAnimations() {
        // Add smooth hover animations to stats cards
        const statsCards = document.querySelectorAll('.stats-card');
        statsCards.forEach(card => {
            card.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-8px)';
            });
            
            card.addEventListener('mouseleave', function() {
                this.style.transform = 'translateY(0)';
            });
        });

        // Add hover effects to action buttons
        const actionBtns = document.querySelectorAll('.action-btn');
        actionBtns.forEach(btn => {
            btn.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-2px)';
            });
            
            btn.addEventListener('mouseleave', function() {
                this.style.transform = 'translateY(0)';
            });
        });

        // Add fade-in animation to dashboard elements
        this.animateElementsOnLoad();
    },

    // Animate elements on page load
    animateElementsOnLoad() {
        const elementsToAnimate = [
            '.page-header',
            '.stats-card',
            '.admin-actions',
            '.search-section',
            '.users-table-container'
        ];

        elementsToAnimate.forEach((selector, index) => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(element => {
                element.style.opacity = '0';
                element.style.transform = 'translateY(20px)';
                
                setTimeout(() => {
                    element.style.transition = 'all 0.6s ease-out';
                    element.style.opacity = '1';
                    element.style.transform = 'translateY(0)';
                }, index * 100);
            });
        });
    },

    // Initialize event listeners
    initEventListeners() {
        // Keyboard shortcuts
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
        
        // Table row click handling
        const tableRows = document.querySelectorAll('.custom-table tbody tr');
        tableRows.forEach(row => {
            row.addEventListener('click', function(e) {
                // Don't trigger if clicking on action buttons
                if (!e.target.closest('.btn-action')) {
                    const userId = this.querySelector('.btn-view')?.getAttribute('onclick')?.match(/\d+/)?.[0];
                    if (userId) {
                        AdminDashboard.viewUser(userId);
                    }
                }
            });
        });
    },

    // Handle keyboard shortcuts
    handleKeyboardShortcuts(e) {
        // Debug logging
        console.log('🔧 Keyboard event:', {
            key: e.key,
            ctrlKey: e.ctrlKey,
            metaKey: e.metaKey,
            keyCode: e.keyCode
        });

        // Ctrl/Cmd + K for search focus
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            console.log('🔍 Ctrl+K pressed - focusing search');
            const searchInput = document.getElementById('userSearch');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
                this.showAlert('Search focused! (Ctrl+K)', 'info', 2000);
            } else {
                console.warn('❌ Search input not found');
            }
            return;
        }

        // Escape to clear search
        if (e.key === 'Escape') {
            const searchInput = document.getElementById('userSearch');
            if (searchInput && searchInput.value) {
                console.log('🧹 Escape pressed - clearing search');
                searchInput.value = '';
                searchInput.dispatchEvent(new Event('input'));
                this.showAlert('Search cleared! (Escape)', 'info', 2000);
            }
            return;
        }

        // Ctrl/Cmd + N for new user
        if ((e.ctrlKey || e.metaKey) && (e.key === 'n' || e.key === 'N')) {
            e.preventDefault();
            console.log('👤 Ctrl+N pressed - new user action');
            this.showCreateUser();
            return;
        }
    },

    // User management functions
    viewUser(userId) {
        if (!userId) {
            this.showAlert('Invalid user ID', 'danger');
            return;
        }
        
        // Add loading state
        this.showAlert('Loading user details...', 'info');
        
        // Navigate to user details page
        window.location.href = `/auth/admin/users/${userId}/view/`;
    },

    editUser(userId) {
        if (!userId) {
            this.showAlert('Invalid user ID', 'danger');
            return;
        }
        
        // Add loading state
        this.showAlert('Loading user editor...', 'info');
        
        // Navigate to user edit page
        window.location.href = `/auth/admin/users/${userId}/edit/`;
    },

    deleteUser(userId) {
        if (!userId) {
            this.showAlert('Invalid user ID', 'danger');
            return;
        }

        // Enhanced confirmation dialog
        const userRow = document.querySelector(`[onclick*="${userId}"]`)?.closest('tr');
        const userName = userRow?.querySelector('.user-details h6')?.textContent || 'this user';
        
        const confirmed = confirm(
            `Are you sure you want to delete ${userName}?\n\n` +
            'This action cannot be undone and will permanently remove:\n' +
            '• User account and profile\n' +
            '• Associated data and permissions\n' +
            '• Login credentials\n\n' +
            'Type "DELETE" to confirm deletion.'
        );

        if (confirmed) {
            // Add loading state
            this.showAlert('Deleting user...', 'warning');
            
            // Implement delete functionality
            window.location.href = `/auth/admin/users/${userId}/delete/`;
        }
    },

    showCreateUser() {
        // Add loading state
        this.showAlert('Loading user creation form...', 'info');
        
        // Navigate to create user page
        window.location.href = `/auth/admin/users/create/`;
    },

    showSystemSettings() {
        this.showAlert('System Settings page coming soon!', 'info');
    },

    showReports() {
        this.showAlert('Reports feature coming soon!', 'info');
    },

    exportUsers() {
        this.showAlert('Preparing user export...', 'info');
        
        // Simulate export process
        setTimeout(() => {
            this.showAlert('Export functionality coming soon!', 'warning');
        }, 1500);
    },

    // Enhanced alert system
    showAlert(message, type = 'info', duration = 5000) {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.admin-alert');
        existingAlerts.forEach(alert => alert.remove());

        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show admin-alert`;
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            border-radius: 12px;
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            max-width: 400px;
        `;
        
        const iconMap = {
            success: 'check-circle',
            danger: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };

        alert.innerHTML = `
            <i class="fas fa-${iconMap[type] || 'info-circle'} me-2"></i>${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, duration);
        }
    },

    // Statistics animation
    animateStats() {
        const statNumbers = document.querySelectorAll('.stats-number');
        statNumbers.forEach(stat => {
            const finalValue = parseInt(stat.textContent.replace(/\D/g, '')) || 0;
            let currentValue = 0;
            const increment = finalValue / 50;
            const timer = setInterval(() => {
                currentValue += increment;
                if (currentValue >= finalValue) {
                    stat.textContent = finalValue;
                    clearInterval(timer);
                } else {
                    stat.textContent = Math.floor(currentValue);
                }
            }, 30);
        });
    },

    // Refresh dashboard data
    refreshData() {
        this.showAlert('Refreshing dashboard data...', 'info');
        
        // Simulate data refresh
        setTimeout(() => {
            location.reload();
        }, 1000);
    },

    // Test keyboard shortcuts (for debugging)
    testKeyboardShortcuts() {
        console.log('🧪 Testing keyboard shortcuts...');
        
        // Test search input existence
        const searchInput = document.getElementById('userSearch');
        console.log('Search input found:', !!searchInput);
        
        // Test if event listener is attached
        console.log('Event listeners attached:', !!this.handleKeyboardShortcuts);
        
        // Test search functionality manually
        if (searchInput) {
            console.log('🧪 Testing search functionality...');
            
            // Test with a sample search
            searchInput.value = 'test';
            searchInput.dispatchEvent(new Event('input'));
            
            setTimeout(() => {
                searchInput.value = '';
                searchInput.dispatchEvent(new Event('input'));
                console.log('🧪 Search test completed');
            }, 2000);
        }
        
        // Simulate Ctrl+K
        console.log('Simulating Ctrl+K...');
        const ctrlKEvent = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true
        });
        document.dispatchEvent(ctrlKEvent);
        
        return {
            searchInput: !!searchInput,
            keyboardHandler: !!this.handleKeyboardShortcuts,
            searchHandler: !!this.searchHandler,
            message: 'Check console for test results'
        };
    },

    // Manual search trigger (for debugging)
    triggerSearch(searchTerm = '') {
        const searchInput = document.getElementById('userSearch');
        if (searchInput) {
            searchInput.value = searchTerm;
            searchInput.dispatchEvent(new Event('input'));
            console.log(`🔍 Manual search triggered for: "${searchTerm}"`);
        } else {
            console.warn('❌ Search input not found');
        }
    }
};

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Wait for base authentication scripts to load
    setTimeout(() => {
        AdminDashboard.init();
        
        // Animate stats after initialization
        setTimeout(() => {
            AdminDashboard.animateStats();
        }, 500);
    }, 100);
});

// Export functions for template usage
window.AdminDashboard = AdminDashboard;

// Legacy function compatibility for existing onclick handlers
window.viewUser = function(userId) {
    AdminDashboard.viewUser(userId);
};

window.editUser = function(userId) {
    AdminDashboard.editUser(userId);
};

window.deleteUser = function(userId) {
    AdminDashboard.deleteUser(userId);
};

window.showCreateUser = function() {
    AdminDashboard.showCreateUser();
};

window.showSystemSettings = function() {
    AdminDashboard.showSystemSettings();
};

window.showReports = function() {
    AdminDashboard.showReports();
};

window.exportUsers = function() {
    AdminDashboard.exportUsers();
};

// Add global keyboard shortcut hints
document.addEventListener('DOMContentLoaded', function() {
    // Initialize AdminDashboard
    AdminDashboard.init();
    
    // Make AdminDashboard globally accessible for debugging
    window.AdminDashboard = AdminDashboard;
    
    // Add keyboard shortcut tooltip to search input
    const searchInput = document.getElementById('userSearch');
    if (searchInput) {
        searchInput.setAttribute('title', 'Press Ctrl+K to focus, Escape to clear');
        searchInput.setAttribute('placeholder', 'Search users by name or email... (Ctrl+K)');
    }
    
    console.log('🔧 AdminDashboard is now available globally. Try: AdminDashboard.testKeyboardShortcuts()');
});
