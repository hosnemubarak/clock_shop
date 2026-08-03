(function() {
    var hasToast = document.querySelectorAll("[toast-list]").length > 0;
    var hasChoices = document.querySelectorAll("[data-choices]").length > 0;
    var hasFlatpickr = document.querySelectorAll("[data-provider]").length > 0;

    function loadScript(src) {
        var script = document.createElement('script');
        script.type = 'text/javascript';
        script.src = src;
        script.async = false;
        document.body.appendChild(script);
    }

    if (hasToast || hasChoices || hasFlatpickr) {
        loadScript('https://cdn.jsdelivr.net/npm/toastify-js');
        loadScript('https://cdn.jsdelivr.net/npm/choices.js/public/assets/scripts/choices.min.js');
        loadScript('https://cdn.jsdelivr.net/npm/flatpickr');
    }
})();