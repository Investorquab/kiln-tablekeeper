(() => {
    const app = document.getElementById("app");
    const restaurants = [];
    const presentation = {
        "demo-ember-oak": {
            cuisine: "Grill / Steakhouse",
            image: "/assets/images/restaurant-ember-oak.webp",
            alt: "Warmly lit dining room at Ember & Oak"
        },
        "demo-green-fork": {
            cuisine: "Italian / Pizza / Pasta",
            image: "/assets/images/restaurant-green-fork.webp",
            alt: "Greenery-filled dining room at The Green Fork"
        },
        "demo-palm-plate": {
            cuisine: "African / Local / Seafood",
            image: "/assets/images/restaurant-palm-plate.webp",
            alt: "Open-air dining at Palm & Plate beside the water"
        },
        "demo-olive-room": {
            cuisine: "Mediterranean / Seafood / Modern",
            image: "/assets/images/restaurant-olive-room.webp",
            alt: "Waterfront dining room at The Olive Room"
        }
    };
    let recordsLoaded = false;
    let handoffApplied = false;

    const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);

    function configureNavigation() {
        const nav = document.querySelector(".nav");
        const brand = nav?.querySelector(".brand");
        if (!nav || !brand) return;
        brand.href = "/welcome";
        if (!brand.querySelector("img")) {
            brand.replaceChildren(Object.assign(document.createElement("img"), {
                src: "/assets/brand/tablekeeper-logo.svg",
                alt: "Tablekeeper"
            }));
        }
        if (!nav.querySelector(".nav-welcome")) {
            const welcome = Object.assign(document.createElement("a"), {
                href: "/welcome",
                textContent: "Welcome",
                className: "nav-welcome"
            });
            nav.insertBefore(welcome, nav.querySelector("#userbar"));
        }
        if (location.pathname === "/welcome") {
            nav.querySelectorAll("a[href]").forEach(link => link.removeAttribute("aria-current"));
            nav.querySelector(".nav-welcome")?.setAttribute("aria-current", "page");
        }
    }

    function cardsMarkup() {
        if (!restaurants.length) {
            return `<div class="visual-empty">${recordsLoaded
                ? "Restaurant details are unavailable right now."
                : "Discovering places for your next meal…"}</div>`;
        }
        return restaurants.map(restaurant => {
            const details = presentation[restaurant.id] || {
                cuisine: "A Tablekeeper restaurant",
                image: "/assets/images/restaurant-detail.webp",
                alt: `Dining room at ${restaurant.name}`
            };
            const tableCount = Array.isArray(restaurant.tables) ? restaurant.tables.length : 0;
            return `<article class="restaurant-card">
                <div class="restaurant-photo"><img src="${details.image}" alt="${escape(details.alt)}" loading="lazy"></div>
                <div class="restaurant-card-body">
                    <span class="restaurant-category">${escape(details.cuisine)}</span>
                    <h3>${escape(restaurant.name)}</h3>
                    <span class="restaurant-meta"><img src="/assets/icons/location.svg" alt="" aria-hidden="true">
                        Local time · ${escape(restaurant.timezone || "restaurant time zone")}</span>
                    <span class="restaurant-meta"><img src="/assets/icons/table.svg" alt="" aria-hidden="true">
                        ${tableCount} tables · choose from live availability</span>
                    <a class="restaurant-action" href="/?restaurant=${encodeURIComponent(restaurant.id)}#search-form"
                       aria-label="See availability at ${escape(restaurant.name)}">
                        <img src="/assets/icons/availability.svg" alt="" aria-hidden="true">See availability
                    </a>
                </div>
            </article>`;
        }).join("");
    }

    function welcomeMarkup() {
        const cards = cardsMarkup();
        return `<div class="welcome-page">
            <section class="welcome-hero" aria-labelledby="welcome-title">
                <div class="welcome-copy">
                    <span class="eyebrow">A table worth gathering around</span>
                    <h1 id="welcome-title">Make room for a good evening.</h1>
                    <p>Discover inviting restaurants, find a time that works, and reserve your table with confidence.</p>
                    <div class="welcome-actions">
                        <a class="welcome-primary" href="/">Find a table <span aria-hidden="true">→</span></a>
                        <a class="welcome-secondary" href="/signup">Join Tablekeeper</a>
                    </div>
                </div>
                <div class="welcome-hero-image">
                    <img src="/assets/images/hero-restaurant.webp" alt="An intimate restaurant set for dinner" fetchpriority="high">
                    <img class="welcome-hero-mark" src="/assets/illustrations/restaurant-line-art.svg" alt="" aria-hidden="true">
                </div>
            </section>
            <section class="welcome-benefits" aria-label="Plan your evening">
                <div class="welcome-benefit"><img src="/assets/icons/search.svg" alt="" aria-hidden="true">Explore a considered collection of restaurants</div>
                <div class="welcome-benefit"><img src="/assets/icons/clock.svg" alt="" aria-hidden="true">Check real-time seating for your date</div>
                <div class="welcome-benefit"><img src="/assets/icons/shield.svg" alt="" aria-hidden="true">Reserve with clear details and a reference</div>
            </section>
            <section class="visual-section" aria-labelledby="welcome-restaurants-title">
                <div class="visual-section-heading">
                    <div><span class="eyebrow">A few places to begin</span><h2 id="welcome-restaurants-title">Find your kind of table</h2></div>
                    <p>Browse our restaurants, then check live tables for the day and party size you have in mind.</p>
                </div>
                <div class="restaurant-cards">${cards}</div>
            </section>
            <section class="visual-promise">
                <img src="/assets/icons/availability.svg" alt="" aria-hidden="true">
                <div><strong>Good plans start with a real table.</strong><p>Every availability choice leads to the restaurant’s live booking flow.</p></div>
                <img class="visual-promise-mark" src="/assets/illustrations/table-setting.svg" alt="" aria-hidden="true">
            </section>
            <footer class="welcome-footer">
                <img src="/assets/brand/tablekeeper-logo.svg" alt="Tablekeeper">
                <span>Discover thoughtfully. Reserve confidently.</span>
            </footer>
        </div>`;
    }

    function renderWelcome() {
        if (app.querySelector(".welcome-page") && (!recordsLoaded || app.dataset.welcomeReady === "true")) return;
        app.innerHTML = welcomeMarkup();
        app.dataset.welcomeReady = recordsLoaded ? "true" : "false";
        document.title = "Welcome to Tablekeeper | Find your table";
    }

    function addRestaurantDiscovery() {
        if (app.querySelector("#restaurant-discovery")) return;
        const discoveryPanel = app.querySelector(".discovery-panel");
        if (!discoveryPanel) return;
        const section = document.createElement("section");
        section.id = "restaurant-discovery";
        section.className = "visual-section";
        section.setAttribute("aria-labelledby", "restaurant-discovery-title");
        section.innerHTML = `<div class="visual-section-heading">
            <div><span class="eyebrow">Explore the collection</span><h2 id="restaurant-discovery-title">A place for every occasion</h2></div>
            <p>Choose a restaurant to search its real tables and times.</p>
        </div><div class="restaurant-cards">${cardsMarkup()}</div>`;
        discoveryPanel.after(section);
    }

    function addConfirmationIllustration() {
        const confirmation = app.querySelector('[data-testid="confirmation"]');
        if (!confirmation || confirmation.querySelector(".confirmation-art")) return;
        const image = Object.assign(document.createElement("img"), {
            src: "/assets/illustrations/reservation-confirmed.svg",
            alt: "",
            className: "confirmation-art"
        });
        image.setAttribute("aria-hidden", "true");
        confirmation.prepend(image);
    }

    function decorateField(selector, asset, label) {
        const input = app.querySelector(selector);
        const parent = input?.closest("label");
        if (!parent || parent.querySelector(".visual-icon-note")) return;
        let note = parent.querySelector(".field-note");
        if (!note) {
            note = document.createElement("span");
            note.className = "field-note";
            parent.append(note);
        }
        note.classList.add("visual-icon-note");
        const icon = Object.assign(document.createElement("img"), {
            src: `/assets/icons/${asset}.svg`,
            alt: ""
        });
        icon.setAttribute("aria-hidden", "true");
        note.prepend(icon);
        if (!note.textContent.trim()) note.append(document.createTextNode(label));
    }

    function decorateFields() {
        decorateField('[data-testid="restaurant-select"]', "location", "Choose a restaurant");
        decorateField('[data-testid="date-input"]', "calendar", "Choose your date");
        decorateField('[data-testid="party-size-input"]', "guests", "Number of guests");
        decorateField('[data-testid="booking-party-size"]', "guests", "Number of guests");
        decorateField('[data-testid="lookup-reference-input"]', "retry", "Your booking reference");
    }

    function applyRestaurantHandoff() {
        if (handoffApplied || location.pathname !== "/") return;
        const restaurantId = new URLSearchParams(location.search).get("restaurant");
        if (!restaurantId) return;
        const select = app.querySelector('[data-testid="restaurant-select"]');
        const form = app.querySelector("#search-form");
        if (!select || !form || !Array.from(select.options).some(option => option.value === restaurantId)) return;
        select.value = restaurantId;
        handoffApplied = true;
        form.requestSubmit();
        app.querySelector("#results")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function enhanceApp() {
        configureNavigation();
        if (location.pathname === "/welcome") {
            renderWelcome();
            return;
        }
        if (location.pathname === "/" && app.querySelector("#search-form")) {
            addRestaurantDiscovery();
            applyRestaurantHandoff();
            if (location.search) document.title = "Find a table | Tablekeeper";
        }
        decorateFields();
        addConfirmationIllustration();
    }

    async function loadRestaurants() {
        try {
            const response = await fetch("/restaurants", { headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const listing = await response.json();
            const details = await Promise.all((listing.restaurants || []).map(async row => {
                const result = await fetch(`/restaurants/${encodeURIComponent(row.id)}`, {
                    headers: { Accept: "application/json" }
                });
                return result.ok ? result.json() : null;
            }));
            restaurants.splice(0, restaurants.length, ...details.filter(Boolean));
        } catch {
            restaurants.length = 0;
        } finally {
            recordsLoaded = true;
            enhanceApp();
        }
    }

    configureNavigation();
    const observer = new MutationObserver(enhanceApp);
    observer.observe(app, { childList: true, subtree: true });
    void loadRestaurants();
    enhanceApp();
})();
