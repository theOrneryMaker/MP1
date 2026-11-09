// theme.js - light/dark for the MP1 pages. Follows the computer's setting unless the
// top-bar toggle picks one (remembered in this browser). Load it in <head> so the page
// never flashes the wrong colours.
(function () {
    var KEY = 'mp1-theme';
    function saved() {
        try { return localStorage.getItem(KEY) || 'auto'; } catch (e) { return 'auto'; }
    }
    function apply(mode) {
        if (mode === 'light' || mode === 'dark') document.documentElement.setAttribute('data-theme', mode);
        else document.documentElement.removeAttribute('data-theme');
        var buttons = document.querySelectorAll('.theme-toggle button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].classList.toggle('on', buttons[i].getAttribute('data-mode') === mode);
        }
    }
    window.setTheme = function (mode) {
        try { localStorage.setItem(KEY, mode); } catch (e) { /* private window: just this visit */ }
        apply(mode);
    };
    apply(saved());
    document.addEventListener('DOMContentLoaded', function () { apply(saved()); });
})();
