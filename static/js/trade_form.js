// Buy / Sell form: shows the limit-price field for limit orders and keeps the
// Order Summary (price, total, cash after) up to date as the customer types and
// as live prices change. The server re-checks everything when the form is
// submitted, so these checks are only to give quick feedback.

(function () {
    const form = document.querySelector("[data-trade-form]");
    if (!form) return;

    const side = form.dataset.side; // "buy" or "sell"
    const cash = parseFloat(form.dataset.cash) || 0;

    const stockSelect = form.querySelector("#stock_id");
    const quantityInput = form.querySelector("#quantity");
    const limitInput = form.querySelector("#limit_price");
    const limitField = form.querySelector("[data-limit-field]");
    const errorBox = form.querySelector("[data-form-error]");
    const sellAll = form.querySelector("[data-sell-all]");
    const out = (name) => form.querySelector(`[data-out="${name}"]`);

    const usd = (n) =>
        "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const selected = () => stockSelect.options[stockSelect.selectedIndex];
    const orderKind = () => form.querySelector('input[name="order_kind"]:checked').value;

    function currentPrice() {
        const option = selected();
        if (!option || !option.value) return null;
        const live = window.athenaPrices && window.athenaPrices[option.value];
        return live ? live.current_price : parseFloat(option.dataset.price);
    }

    function availableVolume() {
        const option = selected();
        const live = option && window.athenaPrices && window.athenaPrices[option.value];
        return live ? live.volume_available : parseInt(option?.dataset.volume || "0", 10);
    }

    function setText(name, text) {
        const el = out(name);
        if (el) el.textContent = text;
    }

    // Remember each hint's original wording, since a hint can be swapped temporarily below.
    form.querySelectorAll("[data-kind-hint]").forEach((el) => {
        el.dataset.original = el.textContent;
    });

    function update() {
        form.querySelectorAll("[data-kind-hint]").forEach((el) => {
            el.textContent = el.dataset.original;
        });

        const isLimit = orderKind() === "limit";
        limitField.hidden = !isLimit;
        limitInput.required = isLimit;
        form.querySelectorAll("[data-kind-hint]").forEach((el) => {
            el.hidden = el.dataset.kindHint !== orderKind();
        });

        const option = selected();
        const current = currentPrice();
        const qty = parseInt(quantityInput.value, 10) || 0;
        const limit = parseFloat(limitInput.value) || 0;

        // Would a limit order fill immediately at today's price?
        const limitFillsNow =
            isLimit && current !== null && limit > 0 &&
            (side === "buy" ? current <= limit : current >= limit);

        const price = isLimit && !limitFillsNow ? limit : current || 0;
        const total = price * qty;

        setText("current", current !== null ? usd(current) : "—");
        setText("price-label", isLimit && !limitFillsNow ? "Limit price" : "Price per share");
        setText("price", price ? usd(price) : "—");
        setText("qty", qty.toLocaleString("en-US"));
        setText("total", usd(total));

        let error = "";

        if (side === "buy") {
            const volume = option && option.value ? availableVolume() : null;
            setText("volume", volume !== null ? volume.toLocaleString("en-US") : "—");
            setText("after", usd(cash - total));

            if (qty > 0 && total > cash) error = `Not enough cash: this order needs ${usd(total)}.`;
            else if (volume !== null && qty > volume) error = `Only ${volume.toLocaleString("en-US")} shares are available.`;
        } else {
            const owned = option && option.value ? parseInt(option.dataset.owned, 10) : null;
            const avg = option && option.value ? parseFloat(option.dataset.avg) : null;
            setText("owned", owned !== null ? owned.toLocaleString("en-US") : "—");
            setText("avg", avg !== null ? usd(avg) : "—");
            // A pending sell doesn't pay out until it fills.
            setText("after", usd(cash + (isLimit && !limitFillsNow ? 0 : total)));

            const gainEl = out("gain");
            if (gainEl) {
                if (avg !== null && qty > 0 && price) {
                    const gain = (price - avg) * qty;
                    gainEl.textContent = (gain >= 0 ? "+" : "−") + usd(Math.abs(gain));
                    gainEl.className = gain > 0 ? "change up" : gain < 0 ? "change down" : "";
                } else {
                    gainEl.textContent = "—";
                    gainEl.className = "";
                }
            }

            if (owned !== null && qty > owned) error = `You only own ${owned.toLocaleString("en-US")} shares.`;
        }

        if (limitFillsNow) {
            const hint = form.querySelector('[data-kind-hint="limit"]');
            if (hint) {
                hint.hidden = false;
                hint.textContent =
                    side === "buy"
                        ? "The price is already at or below your limit, so this will buy right away at the current price."
                        : "The price is already at or above your limit, so this will sell right away at the current price.";
            }
        }

        errorBox.textContent = error;
        errorBox.hidden = !error;
    }

    if (sellAll) {
        sellAll.addEventListener("click", () => {
            const option = selected();
            if (option && option.value) {
                quantityInput.value = option.dataset.owned;
                update();
            }
        });
    }

    form.addEventListener("input", update);
    form.addEventListener("change", update);
    document.addEventListener("prices:update", update);

    form.addEventListener("submit", (event) => {
        update();
        if (!errorBox.hidden) {
            event.preventDefault();
            return;
        }
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
        button.textContent = "Placing order…";
    });

    update();
})();
