/* Clock Shop App JavaScript */

(function() {
    'use strict';

    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Sidebar toggle - Mobile and Desktop
    var verticalMenuBtn = document.getElementById('topnav-hamburger-icon');
    var verticalOverlay = document.querySelector('.vertical-overlay');
    
    function toggleSidebar() {
        if (window.innerWidth < 1025) {
            // Mobile: Toggle sidebar visibility
            document.body.classList.toggle('sidebar-enable');
            if (document.body.classList.contains('sidebar-enable')) {
                if (verticalOverlay) {
                    verticalOverlay.style.display = 'block';
                }
            } else {
                if (verticalOverlay) {
                    verticalOverlay.style.display = 'none';
                }
            }
        } else {
            // Desktop: Toggle sidebar size
            var currentSize = document.documentElement.getAttribute('data-sidebar-size');
            document.documentElement.setAttribute('data-sidebar-size', currentSize === 'sm' ? 'lg' : 'sm');
        }
    }
    
    function closeSidebarMobile() {
        document.body.classList.remove('sidebar-enable');
        if (verticalOverlay) {
            verticalOverlay.style.display = 'none';
        }
    }
    
    if (verticalMenuBtn) {
        verticalMenuBtn.addEventListener('click', function(e) {
            e.preventDefault();
            toggleSidebar();
        });
    }
    
    // Close sidebar when clicking overlay (mobile)
    if (verticalOverlay) {
        verticalOverlay.addEventListener('click', function() {
            closeSidebarMobile();
        });
    }
    
    // Close sidebar on window resize to desktop
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 1025) {
            document.body.classList.remove('sidebar-enable');
            if (verticalOverlay) {
                verticalOverlay.style.display = 'none';
            }
        }
    });
    
    // Close sidebar when clicking a nav link on mobile
    var navLinks = document.querySelectorAll('.navbar-nav .nav-link:not([data-bs-toggle])');
    navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            if (window.innerWidth < 1025) {
                closeSidebarMobile();
            }
        });
    });

    // Active menu item
    var currentUrl = window.location.href;
    var menuLinks = document.querySelectorAll('.navbar-nav .nav-link');
    menuLinks.forEach(function(link) {
        if (link.href === currentUrl) {
            link.classList.add('active');
            var parent = link.closest('.menu-dropdown');
            if (parent) {
                parent.classList.add('show');
                var parentLink = parent.previousElementSibling;
                if (parentLink) {
                    parentLink.classList.add('active');
                    parentLink.setAttribute('aria-expanded', 'true');
                }
            }
        }
    });

    // Back to top button
    var backToTopBtn = document.getElementById('back-to-top');
    if (backToTopBtn) {
        window.onscroll = function() {
            if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
                backToTopBtn.style.display = 'block';
            } else {
                backToTopBtn.style.display = 'none';
            }
        };
    }

    // Fullscreen toggle
    var fullscreenBtn = document.querySelector('[data-toggle="fullscreen"]');
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', function() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        });
    }

    // Dark/Light mode toggle
    var modeBtn = document.querySelector('.light-dark-mode');
    if (modeBtn) {
        modeBtn.addEventListener('click', function() {
            var currentTheme = document.documentElement.getAttribute('data-bs-theme');
            var newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-bs-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        });

        // Load saved theme
        var savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-bs-theme', savedTheme);
        }
    }

    // Auto-hide alerts after 5 seconds
    var alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

})();

// Helper function for top scroll
function topFunction() {
    document.body.scrollTop = 0;
    document.documentElement.scrollTop = 0;
}

// CSRF token helper for AJAX requests
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Setup AJAX CSRF
const csrftoken = getCookie('csrftoken');

// Modal Helper Functions
function showValidationModal(message, title = 'Attention') {
    document.getElementById('validationModalTitle').textContent = title;
    document.getElementById('validationModalMessage').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('validationModal'));
    modal.show();
}

function showErrorModal(message, title = 'Error') {
    document.getElementById('errorModalTitle').textContent = title;
    document.getElementById('errorModalMessage').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('errorModal'));
    modal.show();
}

function showSuccessModal(message, title = 'Success') {
    document.getElementById('successModalTitle').textContent = title;
    document.getElementById('successModalMessage').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('successModal'));
    modal.show();
}

function showConfirmModal(message, title = 'Confirm Action', callback) {
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalMessage').textContent = message;
    
    const confirmBtn = document.getElementById('confirmModalBtn');
    const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
    
    // Remove old event listeners
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    
    newConfirmBtn.addEventListener('click', function() {
        modal.hide();
        if (typeof callback === 'function') {
            callback();
        }
    });
    
    modal.show();
}
