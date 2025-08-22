/**
 * HelixBridge - Authentication JavaScript
 * Login, Register, and Authentication Form Functionality
 */

const AuthForms = {
    // Login form functionality
    login: {
        /**
         * Initialize login form
         */
        init() {
            const loginForm = document.getElementById('loginForm');
            if (!loginForm) return;

            // Add form validation and submission
            HelixAuth.form.handleSubmit(loginForm, this.handleLogin);

            // Add remember me functionality
            this.initRememberMe();

            // Add social login handlers
            this.initSocialLogin();

            // Add forgot password handler
            this.initForgotPassword();

            console.log('🔐 Login form initialized');
        },

        /**
         * Handle login form submission
         * @param {HTMLFormElement} form - Login form element
         */
        handleLogin(form) {
            const submitBtn = form.querySelector('button[type="submit"]');
            const email = form.querySelector('input[type="email"]').value;
            const password = form.querySelector('input[type="password"]').value;

            // Show loading state
            HelixAuth.ui.setButtonLoading(submitBtn, 'Signing in...');

            // Validate email format
            if (!HelixAuth.validation.isValidEmail(email)) {
                HelixAuth.ui.removeButtonLoading(submitBtn);
                HelixAuth.ui.showAlert('Please enter a valid email address', 'danger', form.parentNode);
                return;
            }

            // Submit form (this will be handled by Django)
            setTimeout(() => {
                form.submit();
            }, 500);
        },

        /**
         * Initialize remember me functionality
         */
        initRememberMe() {
            const rememberCheckbox = document.getElementById('rememberMe');
            if (!rememberCheckbox) return;

            // Load saved email if remember me was checked
            const savedEmail = localStorage.getItem('helix_remembered_email');
            if (savedEmail) {
                const emailInput = document.querySelector('input[type="email"]');
                if (emailInput) {
                    emailInput.value = savedEmail;
                    rememberCheckbox.checked = true;
                }
            }

            // Save/remove email based on checkbox
            rememberCheckbox.addEventListener('change', function() {
                const emailInput = document.querySelector('input[type="email"]');
                if (this.checked && emailInput && emailInput.value) {
                    localStorage.setItem('helix_remembered_email', emailInput.value);
                } else {
                    localStorage.removeItem('helix_remembered_email');
                }
            });
        },

        /**
         * Initialize social login buttons
         */
        initSocialLogin() {
            const socialButtons = document.querySelectorAll('.btn-social');
            socialButtons.forEach(button => {
                button.addEventListener('click', function() {
                    const provider = this.dataset.provider || 'unknown';
                    AuthForms.ui.showFeatureComingSoon(`${provider} login`);
                });
            });
        },

        /**
         * Initialize forgot password link
         */
        initForgotPassword() {
            const forgotLink = document.querySelector('.forgot-password a');
            if (forgotLink) {
                forgotLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    AuthForms.ui.showForgotPasswordModal();
                });
            }
        }
    },

    // Register form functionality
    register: {
        /**
         * Initialize register form
         */
        init() {
            const registerForm = document.getElementById('registerForm');
            if (!registerForm) return;

            // Add form validation and submission
            HelixAuth.form.handleSubmit(registerForm, this.handleRegister);

            // Initialize password strength meter
            this.initPasswordStrength();

            // Initialize confirm password validation
            this.initConfirmPassword();

            // Add social register handlers
            this.initSocialRegister();

            console.log('📝 Register form initialized');
        },

        /**
         * Handle register form submission
         * @param {HTMLFormElement} form - Register form element
         */
        handleRegister(form) {
            const submitBtn = form.querySelector('button[type="submit"]');
            const formData = new FormData(form);

            // Show loading state
            HelixAuth.ui.setButtonLoading(submitBtn, 'Creating account...');

            // Additional validation
            if (!this.validateRegistration(form)) {
                HelixAuth.ui.removeButtonLoading(submitBtn);
                return;
            }

            // Submit form (this will be handled by Django)
            setTimeout(() => {
                form.submit();
            }, 500);
        },

        /**
         * Validate registration form
         * @param {HTMLFormElement} form - Register form element
         * @returns {boolean} - True if valid
         */
        validateRegistration(form) {
            const password = form.querySelector('input[name="password"]').value;
            const confirmPassword = form.querySelector('input[name="confirm_password"]').value;
            const email = form.querySelector('input[name="email"]').value;

            // Check password strength
            const passwordValidation = HelixAuth.validation.validatePassword(password);
            if (!passwordValidation.isValid) {
                HelixAuth.ui.showAlert('Password does not meet security requirements', 'danger', form.parentNode);
                return false;
            }

            // Check password confirmation
            if (password !== confirmPassword) {
                HelixAuth.ui.showAlert('Passwords do not match', 'danger', form.parentNode);
                return false;
            }

            // Check email format
            if (!HelixAuth.validation.isValidEmail(email)) {
                HelixAuth.ui.showAlert('Please enter a valid email address', 'danger', form.parentNode);
                return false;
            }

            return true;
        },

        /**
         * Initialize password strength meter
         */
        initPasswordStrength() {
            const passwordInput = document.querySelector('input[name="password"]');
            const strengthMeter = document.querySelector('.strength-meter');
            const requirements = document.querySelector('.password-requirements');

            if (!passwordInput) return;

            passwordInput.addEventListener('input', function() {
                HelixAuth.ui.updatePasswordStrength(this.value, strengthMeter, requirements);
            });
        },

        /**
         * Initialize confirm password validation
         */
        initConfirmPassword() {
            const passwordInput = document.querySelector('input[name="password"]');
            const confirmInput = document.querySelector('input[name="confirm_password"]');

            if (!passwordInput || !confirmInput) return;

            const validateConfirmPassword = () => {
                if (confirmInput.value && passwordInput.value !== confirmInput.value) {
                    confirmInput.classList.add('is-invalid');
                    confirmInput.classList.remove('is-valid');
                    
                    let feedback = confirmInput.parentNode.querySelector('.invalid-feedback');
                    if (!feedback) {
                        feedback = document.createElement('div');
                        feedback.className = 'invalid-feedback';
                        confirmInput.parentNode.appendChild(feedback);
                    }
                    feedback.textContent = 'Passwords do not match';
                } else if (confirmInput.value) {
                    confirmInput.classList.remove('is-invalid');
                    confirmInput.classList.add('is-valid');
                    
                    const feedback = confirmInput.parentNode.querySelector('.invalid-feedback');
                    if (feedback) {
                        feedback.remove();
                    }
                }
            };

            confirmInput.addEventListener('input', validateConfirmPassword);
            passwordInput.addEventListener('input', validateConfirmPassword);
        },

        /**
         * Initialize social register buttons
         */
        initSocialRegister() {
            const socialButtons = document.querySelectorAll('.btn-social');
            socialButtons.forEach(button => {
                button.addEventListener('click', function() {
                    const provider = this.dataset.provider || 'unknown';
                    AuthForms.ui.showFeatureComingSoon(`${provider} registration`);
                });
            });
        }
    },

    // UI utilities specific to authentication
    ui: {
        /**
         * Show feature coming soon message
         * @param {string} feature - Feature name
         */
        showFeatureComingSoon(feature = 'This feature') {
            HelixAuth.ui.showAlert(`${feature} is coming soon!`, 'info');
        },

        /**
         * Show forgot password modal
         */
        showForgotPasswordModal() {
            // Create modal HTML
            const modalHTML = `
                <div class="modal fade" id="forgotPasswordModal" tabindex="-1" aria-labelledby="forgotPasswordModalLabel" aria-hidden="true">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content" style="border-radius: 20px; border: none; backdrop-filter: blur(20px);">
                            <div class="modal-header" style="border-bottom: 1px solid rgba(0,0,0,0.1);">
                                <h5 class="modal-title" id="forgotPasswordModalLabel">
                                    <i class="fas fa-key me-2"></i>Reset Password
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <p class="text-muted mb-3">Enter your email address and we'll send you a link to reset your password.</p>
                                <form id="forgotPasswordForm">
                                    <div class="form-floating mb-3">
                                        <input type="email" class="form-control" id="forgotEmail" placeholder="name@example.com" required>
                                        <label for="forgotEmail">Email address</label>
                                    </div>
                                    <button type="submit" class="btn btn-primary w-100">
                                        <i class="fas fa-paper-plane me-2"></i>Send Reset Link
                                    </button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Remove existing modal if present
            const existingModal = document.getElementById('forgotPasswordModal');
            if (existingModal) {
                existingModal.remove();
            }

            // Add modal to body
            document.body.insertAdjacentHTML('beforeend', modalHTML);

            // Initialize and show modal
            if (typeof bootstrap !== 'undefined') {
                const modal = new bootstrap.Modal(document.getElementById('forgotPasswordModal'));
                modal.show();

                // Handle form submission
                const form = document.getElementById('forgotPasswordForm');
                form.addEventListener('submit', function(e) {
                    e.preventDefault();
                    const email = document.getElementById('forgotEmail').value;
                    
                    if (HelixAuth.validation.isValidEmail(email)) {
                        HelixAuth.ui.showAlert('Password reset link sent! Check your email.', 'success');
                        modal.hide();
                    } else {
                        HelixAuth.ui.showAlert('Please enter a valid email address', 'danger', form.parentNode);
                    }
                });
            }
        },

        /**
         * Initialize page-specific animations
         */
        initAnimations() {
            // Animate form container on load
            const authContainer = document.querySelector('.login-container, .signup-container');
            if (authContainer) {
                authContainer.style.opacity = '0';
                authContainer.style.transform = 'translateY(30px)';
                
                setTimeout(() => {
                    authContainer.style.transition = 'all 0.6s ease-out';
                    authContainer.style.opacity = '1';
                    authContainer.style.transform = 'translateY(0)';
                }, 100);
            }

            // Add hover effects to social buttons
            const socialButtons = document.querySelectorAll('.btn-social');
            socialButtons.forEach(button => {
                button.addEventListener('mouseenter', function() {
                    this.style.transform = 'translateY(-2px) scale(1.02)';
                });
                
                button.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0) scale(1)';
                });
            });
        }
    },

    // Initialize all authentication forms
    init() {
        // Initialize based on current page
        this.login.init();
        this.register.init();
        this.ui.initAnimations();

        // Add global keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            // Enter key on social buttons
            if (e.key === 'Enter' && e.target.classList.contains('btn-social')) {
                e.target.click();
            }
            
            // Escape key to close modals
            if (e.key === 'Escape') {
                const modal = document.querySelector('.modal.show');
                if (modal && typeof bootstrap !== 'undefined') {
                    const modalInstance = bootstrap.Modal.getInstance(modal);
                    if (modalInstance) {
                        modalInstance.hide();
                    }
                }
            }
        });

        console.log('🚀 Authentication forms initialized');
    }
};

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for HelixAuth to initialize first
    setTimeout(() => {
        AuthForms.init();
    }, 100);
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AuthForms;
}

// Add to global scope for template usage
window.AuthForms = AuthForms;
