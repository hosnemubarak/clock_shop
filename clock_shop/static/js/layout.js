/* Layout JavaScript */
(function() {
    'use strict';
    
    // Set default attributes
    if (!document.documentElement.hasAttribute('data-sidebar-size')) {
        document.documentElement.setAttribute('data-sidebar-size', 'lg');
    }
    if (!document.documentElement.hasAttribute('data-bs-theme')) {
        document.documentElement.setAttribute('data-bs-theme', 'light');
    }
})();
