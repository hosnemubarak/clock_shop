/**
 * Chart helpers shared by dashboard and reports (ApexCharts).
 *
 * getChartColorsArray reads a `data-colors` JSON attribute off an element and
 * resolves any CSS custom-property names against :root, matching the Velzon
 * theme convention. Load this before the page's ApexCharts init script.
 */
(function (window, document) {
    'use strict';

    var DEFAULT_COLORS = ["#042A52", "#0ab39c", "#f7b84b"];

    /**
     * @param {string} id       element id carrying the data-colors attribute
     * @param {string[]} [fallback] colors to use when the element/attr is absent
     */
    function getChartColorsArray(id, fallback) {
        var el = document.getElementById(id);
        if (el) {
            var colors = el.getAttribute("data-colors");
            if (colors) {
                colors = JSON.parse(colors);
                return colors.map(function (color) {
                    var c = color.replace(" ", "");
                    if (c.indexOf(",") === -1) {
                        var style = getComputedStyle(document.documentElement);
                        return style.getPropertyValue(c) || c;
                    }
                    return c;
                });
            }
        }
        return fallback || DEFAULT_COLORS;
    }

    window.getChartColorsArray = getChartColorsArray;
})(window, document);
