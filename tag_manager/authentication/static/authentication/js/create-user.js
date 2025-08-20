/**
 * Create User Form Enhancement Script
 * Provides form validation, password confirmation, and user interaction enhancements
 */

const CreateUserForm = {
    init() {
        this.bindEvents();
        this.setupPasswordValidation();
        this.setupFormAnimations();
        console.log('CreateUserForm initialized successfully');
    },

    bindEvents() {
        const form = document.getElementById('createUserForm');
        if (form) {
            form.addEventListener('submit', this.handleFormSubmit.bind(this));
        }
    },

    setupPasswordValidation() {
        const password1 = document.querySelector('#id_password1');
        const password2 = document.querySelector('#id_password2');
        
        if (password1 && password2) {
            password2.addEventListener('input', () => {
                this.validatePasswordMatch(password1, password2);
            });
            
            password1.addEventListener('input', () => {
                if (password2.value) {
                    this.validatePasswordMatch(password1, password2);
                }
            });
        }
    },

    validatePasswordMatch(password1, password2) {
        if (password2.value && password2.value !== password1.value) {
            password2.setCustomValidity('Passwords do not match');
            password2.classList.add('validation-error');
        } else {
            password2.setCustomValidity('');
            password2.classList.remove('validation-error');
        }
    },

    setupFormAnimations() {
        const inputs = document.querySelectorAll('.form-control, .form-select');
        
        inputs.forEach(input => {
            input.addEventListener('focus', (e) => {
                const floatingDiv = e.target.closest('.form-floating');
                if (floatingDiv) {
                    floatingDiv.classList.add('focused');
                }
            });
            
            input.addEventListener('blur', (e) => {
                const floatingDiv = e.target.closest('.form-floating');
                if (floatingDiv) {
                    floatingDiv.classList.remove('focused');
                }
            });
        });
    },

    handleFormSubmit(e) {
        const form = e.target;
        const formData = new FormData(form);
        
        // Basic validation
        const requiredFields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2'];
        const missingFields = [];
        
        requiredFields.forEach(field => {
            if (!formData.get(field) || formData.get(field).trim() === '') {
                missingFields.push(field);
            }
        });
        
        if (missingFields.length > 0) {
            e.preventDefault();
            this.showAlert('Please fill in all required fields', 'danger');
            return false;
        }
        
        // Password validation
        const password1 = formData.get('password1');
        const password2 = formData.get('password2');
        
        if (password1 !== password2) {
            e.preventDefault();
            this.showAlert('Passwords do not match', 'danger');
            return false;
        }
        
        if (password1.length < 8) {
            e.preventDefault();
            this.showAlert('Password must be at least 8 characters long', 'danger');
            return false;
        }
        
        // Email validation
        const email = formData.get('email');
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            e.preventDefault();
            this.showAlert('Please enter a valid email address', 'danger');
            return false;
        }
        
        // If we get here, form is valid
        this.showAlert('Creating user...', 'info');
        return true;
    },

    showAlert(message, type = 'info') {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.dynamic-alert');
        existingAlerts.forEach(alert => alert.remove());
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show dynamic-alert`;
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            border-radius: 12px;
            min-width: 300px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        `;
        
        const icon = this.getAlertIcon(type);
        alert.innerHTML = `
            <i class="${icon} me-2"></i>${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        document.body.appendChild(alert);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.classList.remove('show');
                setTimeout(() => alert.remove(), 300);
            }
        }, 5000);
    },

    getAlertIcon(type) {
        const icons = {
            'success': 'fas fa-check-circle',
            'danger': 'fas fa-exclamation-circle',
            'warning': 'fas fa-exclamation-triangle',
            'info': 'fas fa-info-circle'
        };
        return icons[type] || icons.info;
    },

    // Utility function for manual testing
    testValidation() {
        console.log('Testing form validation...');
        
        // Test password mismatch
        const password1 = document.querySelector('#id_password1');
        const password2 = document.querySelector('#id_password2');
        
        if (password1 && password2) {
            password1.value = 'test123';
            password2.value = 'test456';
            this.validatePasswordMatch(password1, password2);
            console.log('Password mismatch test completed');
            
            // Reset
            password1.value = '';
            password2.value = '';
            password2.setCustomValidity('');
            password2.classList.remove('validation-error');
        }
        
        // Test alert
        this.showAlert('Test alert message', 'warning');
        console.log('Validation tests completed');
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    CreateUserForm.init();
});

// Make available globally for debugging
window.CreateUserForm = CreateUserForm;
