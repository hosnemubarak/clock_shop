(function() {
    // Load Flatpickr only on pages that use date-picker inputs.
    // Choices.js and Toastify are not used in this project:
    // - Dropdowns use TomSelect instead of Choices.js
    // - Notifications use Bootstrap alerts + modals.js instead of Toastify
    var hasFlatpickr = document.querySelectorAll("[data-provider]").length > 0;

    function loadScript(src) {
        var script = document.createElement('script');
        script.type = 'text/javascript';
        script.src = src;
        script.async = false;
        document.body.appendChild(script);
    }

    if (hasFlatpickr) {
        loadScript('https://cdn.jsdelivr.net/npm/flatpickr');
    }
})();