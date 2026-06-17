(function() {
    var hasToast = document.querySelectorAll("[toast-list]").length > 0;
    var hasChoices = document.querySelectorAll("[data-choices]").length > 0;
    var hasProvider = document.querySelectorAll("[data-provider]").length > 0;

    if (hasToast || hasChoices || hasProvider) {
        if (hasToast) {
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css';
            document.head.appendChild(link);
            
            var script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/toastify-js';
            script.async = true;
            document.body.appendChild(script);
        }
        if (hasChoices) {
            var script = document.createElement('script');
            script.src = '/static/libs/choices.js/public/assets/scripts/choices.min.js';
            script.async = true;
            document.body.appendChild(script);
        }
        if (hasProvider) {
            var script = document.createElement('script');
            script.src = '/static/libs/flatpickr/flatpickr.min.js';
            script.async = true;
            document.body.appendChild(script);
        }
    }
})();