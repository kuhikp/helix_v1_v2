/**
 * Helix Tag Manager - Base JavaScript Utilities
 * Common functionality for authentication module
 */

// Utility Functions
const HelixAuth = {
    // Validation utilities
    validation: {
        /**
         * Validate email format
         * @param {string} email - Email to validate
         * @returns {boolean} - True if valid
         */
        isValidEmail(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },

        /**
         * Validate password strength
         * @param {string} password - Password to validate
         * @returns {object} - Validation result with score and requirements
         */
        validatePassword(password) {
            const requirements = {
                length: password.length >= 8,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /\d/.test(password),
                special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
            };

            const score = Object.values(requirements).filter(Boolean).length;
            let strength = 'weak';
            
            if (score >= 5) strength = 'strong';
            else if (score >= 4) strength = 'good';
            else if (score >= 3) strength = 'fair';

            return {
                score,
                strength,
                requirements,
                isValid: score >= 4
            };
        },

        /**
         * Validate form field
         * @param {HTMLElement} field - Form field to validate
         * @returns {boolean} - True if valid
         */
        validateField(field) {
            const value = field.value.trim();
            const type = field.type;
            let isValid = true;
            let message = '';

            // Required field validation
            if (field.hasAttribute('required') && !value) {
                isValid = false;
                message = 'This field is required';
            }
            // Email validation
            else if (type === 'email' && value && !this.isValidEmail(value)) {
                isValid = false;
                message = 'Please enter a valid email address';
            }
            // Password validation
            else if (type === 'password' && value) {
                const validation = this.validatePassword(value);
                if (!validation.isValid) {
                    isValid = false;
                    message = 'Password must meet security requirements';
                }
            }

            return { isValid, message };
        }
    },

    // UI utilities
    ui: {
        /**
         * Show alert message
         * @param {string} message - Alert message
         * @param {string} type - Alert type (success, danger, warning, info)
         * @param {HTMLElement} container - Container element
         * @param {number} duration - Auto-hide duration in ms
         */
        showAlert(message, type = 'info', container = document.body, duration = 5000) {
            // Remove existing alerts
            const existingAlerts = container.querySelectorAll('.alert');
            existingAlerts.forEach(alert => alert.remove());
            
            // Create alert element
            const alert = document.createElement('div');
            alert.className = `alert alert-${type} alert-dismissible fade show`;
            alert.style.position = 'relative';
            alert.style.zIndex = '1050';
            
            // Alert content
            alert.innerHTML = `
                <i class="fas fa-${this.getAlertIcon(type)} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            
            // Insert alert
            const firstChild = container.firstChild;
            if (firstChild) {
                container.insertBefore(alert, firstChild);
            } else {
                container.appendChild(alert);
            }
            
            // Auto-hide after duration
            if (duration > 0) {
                setTimeout(() => {
                    if (alert.parentNode) {
                        alert.remove();
                    }
                }, duration);
            }

            return alert;
        },

        /**
         * Get appropriate icon for alert type
         * @param {string} type - Alert type
         * @returns {string} - FontAwesome icon class
         */
        getAlertIcon(type) {
            const icons = {
                success: 'check-circle',
                danger: 'exclamation-circle',
                warning: 'exclamation-triangle',
                info: 'info-circle'
            };
            return icons[type] || 'info-circle';
        },

        /**
         * Add loading state to button
         * @param {HTMLElement} button - Button element
         * @param {string} loadingText - Loading text
         */
        setButtonLoading(button, loadingText = 'Loading...') {
            button.dataset.originalText = button.textContent;
            button.textContent = loadingText;
            button.classList.add('btn-loading');
            button.disabled = true;
        },

        /**
         * Remove loading state from button
         * @param {HTMLElement} button - Button element
         */
        removeButtonLoading(button) {
            button.textContent = button.dataset.originalText || button.textContent;
            button.classList.remove('btn-loading');
            button.disabled = false;
        },

        /**
         * Animate element entrance
         * @param {HTMLElement} element - Element to animate
         * @param {string} animation - Animation class
         */
        animateIn(element, animation = 'fadeIn') {
            element.style.animation = `${animation} 0.6s ease-out`;
        },

        /**
         * Update password strength indicator
         * @param {string} password - Password value
         * @param {HTMLElement} meterElement - Strength meter element
         * @param {HTMLElement} requirementsElement - Requirements list element
         */
        updatePasswordStrength(password, meterElement, requirementsElement) {
            const validation = this.validation.validatePassword(password);
            
            // Update strength meter
            if (meterElement) {
                const fill = meterElement.querySelector('.strength-fill');
                if (fill) {
                    fill.className = `strength-fill strength-${validation.strength}`;
                }
            }

            // Update requirements list
            if (requirementsElement) {
                const requirements = requirementsElement.querySelectorAll('.requirement');
                requirements.forEach((req, index) => {
                    const reqTypes = ['length', 'uppercase', 'lowercase', 'number', 'special'];
                    const reqType = reqTypes[index];
                    if (reqType && validation.requirements[reqType]) {
                        req.classList.add('met');
                        const icon = req.querySelector('i');
                        if (icon) {
                            icon.className = 'fas fa-check';
                        }
                    } else {
                        req.classList.remove('met');
                        const icon = req.querySelector('i');
                        if (icon) {
                            icon.className = 'fas fa-times';
                        }
                    }
                });
            }
        }
    },

    // Form utilities
    form: {
        /**
         * Handle form submission with validation
         * @param {HTMLFormElement} form - Form element
         * @param {Function} submitCallback - Callback function for submission
         */
        handleSubmit(form, submitCallback) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                
                // Validate all fields
                const fields = form.querySelectorAll('input, select, textarea');
                let isFormValid = true;
                
                fields.forEach(field => {
                    const validation = HelixAuth.validation.validateField(field);
                    
                    if (!validation.isValid) {
                        isFormValid = false;
                        field.classList.add('is-invalid');
                        
                        // Show error message
                        let feedback = field.parentNode.querySelector('.invalid-feedback');
                        if (!feedback) {
                            feedback = document.createElement('div');
                            feedback.className = 'invalid-feedback';
                            field.parentNode.appendChild(feedback);
                        }
                        feedback.textContent = validation.message;
                    } else {
                        field.classList.remove('is-invalid');
                        field.classList.add('is-valid');
                        
                        // Remove error message
                        const feedback = field.parentNode.querySelector('.invalid-feedback');
                        if (feedback) {
                            feedback.remove();
                        }
                    }
                });
                
                if (isFormValid && typeof submitCallback === 'function') {
                    submitCallback(form);
                }
            });
        },

        /**
         * Add real-time validation to form fields
         * @param {HTMLFormElement} form - Form element
         */
        addRealTimeValidation(form) {
            const fields = form.querySelectorAll('input, select, textarea');
            
            fields.forEach(field => {
                // Validate on blur
                field.addEventListener('blur', () => {
                    const validation = HelixAuth.validation.validateField(field);
                    
                    if (!validation.isValid && field.value.trim()) {
                        field.classList.add('is-invalid');
                        field.classList.remove('is-valid');
                    } else if (field.value.trim()) {
                        field.classList.remove('is-invalid');
                        field.classList.add('is-valid');
                    }
                });

                // Clear validation on input
                field.addEventListener('input', () => {
                    if (field.classList.contains('is-invalid')) {
                        field.classList.remove('is-invalid');
                    }
                });

                // Special handling for password fields
                if (field.type === 'password') {
                    field.addEventListener('input', () => {
                        const meter = document.querySelector('.strength-meter');
                        const requirements = document.querySelector('.password-requirements');
                        
                        if (meter || requirements) {
                            HelixAuth.ui.updatePasswordStrength(field.value, meter, requirements);
                        }
                    });
                }
            });
        }
    },

    // Initialize authentication module
    init() {
        console.log('🎯 Helix Authentication Module Initialized');
        
        // Initialize tooltips if Bootstrap is available
        if (typeof bootstrap !== 'undefined') {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }

        // Initialize smooth scrolling
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });

        // Add form validation to all forms with .auth-form class
        document.querySelectorAll('.auth-form').forEach(form => {
            this.form.addRealTimeValidation(form);
        });

        // Add enhanced focus states
        document.querySelectorAll('.form-control').forEach(input => {
            input.addEventListener('focus', function() {
                this.parentNode.classList.add('focused');
            });
            
            input.addEventListener('blur', function() {
                this.parentNode.classList.remove('focused');
            });
        });

        // Initialize navbar collapse for mobile
        const navbarToggler = document.querySelector('.navbar-toggler');
        if (navbarToggler) {
            navbarToggler.addEventListener('click', function() {
                this.classList.toggle('active');
            });
        }
    }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = HelixAuth;
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    HelixAuth.init();
});

// Add global utilities to window for template usage
window.HelixAuth = HelixAuth;
