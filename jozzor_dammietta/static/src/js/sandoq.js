/* Sandoq - Made in Damietta
   Vanilla JS (no framework): category tabs, live search, favourites and the
   mobile menu. Written as a plain script so it works in any Odoo frontend
   bundle without depending on framework-internal module paths. */
(function () {
    "use strict";

    function init() {
        var root = document.querySelector(".sq-page");
        if (!root || root.dataset.sqReady) {
            return;
        }
        root.dataset.sqReady = "1";

        /* ---------- mobile menu ---------- */
        var header = root.querySelector("#sq-header");
        var toggle = root.querySelector("#sq-menu-toggle");
        var mobileNav = root.querySelector("#sq-mobile-nav");

        function setMenu(open) {
            header.classList.toggle("is-open", open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
            toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
            mobileNav.hidden = !open;
        }
        if (toggle && mobileNav && header) {
            toggle.addEventListener("click", function () {
                setMenu(mobileNav.hidden);
            });
            mobileNav.addEventListener("click", function (ev) {
                if (ev.target.closest("a")) {
                    setMenu(false);
                }
            });
        }

        /* ---------- filter + search ---------- */
        var cards = Array.prototype.slice.call(root.querySelectorAll(".sq-card"));
        var tabs = Array.prototype.slice.call(root.querySelectorAll(".sq-tab"));
        var input = root.querySelector("#sq-search-input");
        var emptyMsg = root.querySelector("#sq-empty");
        var activeCategory = "All furniture";

        function applyFilters() {
            var query = (input ? input.value : "").trim().toLowerCase();
            var visible = 0;
            cards.forEach(function (card) {
                var okCategory = activeCategory === "All furniture" || card.dataset.category === activeCategory;
                var okQuery = !query || (card.dataset.search || "").indexOf(query) !== -1;
                var show = okCategory && okQuery;
                card.hidden = !show;
                if (show) {
                    visible += 1;
                }
            });
            if (emptyMsg) {
                emptyMsg.hidden = visible !== 0;
            }
        }

        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                activeCategory = tab.dataset.category;
                tabs.forEach(function (t) {
                    var on = t === tab;
                    t.classList.toggle("is-active", on);
                    t.setAttribute("aria-selected", on ? "true" : "false");
                });
                applyFilters();
            });
        });

        if (input) {
            input.addEventListener("input", applyFilters);
        }

        /* ---------- favourites ---------- */
        root.querySelectorAll(".sq-fav").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var on = !btn.classList.contains("is-active");
                btn.classList.toggle("is-active", on);
                btn.setAttribute("aria-pressed", on ? "true" : "false");
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
