// Live prices: asks the server for the latest stock prices every few seconds
// and updates any table row marked with data-stock-id. Pages can also listen
// for the "prices:update" event (the Buy and Sell pages do, to recalculate totals).

(function () {
    const REFRESH_MS = 5000;

    const usd = (n) =>
        n === null || n === undefined
            ? "—"
            : "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const compactUsd = (n) => {
        const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"]];
        for (const [size, suffix] of units) {
            if (n >= size) return "$" + (n / size).toFixed(2) + suffix;
        }
        return usd(n);
    };

    window.athenaPrices = {};

    function setText(row, field, text) {
        const cell = row.querySelector(`[data-field="${field}"]`);
        if (cell && cell.textContent.trim() !== text) cell.textContent = text;
        return cell;
    }

    function updateRow(row, s) {
        const priceCell = row.querySelector('[data-field="current_price"]');
        const before = priceCell ? priceCell.textContent.trim() : null;

        setText(row, "current_price", usd(s.current_price));
        setText(row, "open_price", usd(s.open_price));
        setText(row, "day_high", usd(s.day_high));
        setText(row, "day_low", usd(s.day_low));
        setText(row, "volume_available", s.volume_available.toLocaleString("en-US"));
        setText(row, "market_cap", compactUsd(s.current_price * s.volume_available));

        const changeCell = row.querySelector('[data-field="change"]');
        if (changeCell && s.open_price) {
            const pct = ((s.current_price - s.open_price) / s.open_price) * 100;
            const dir = pct > 0 ? "up" : pct < 0 ? "down" : "";
            changeCell.innerHTML =
                `<span class="change ${dir}">${pct > 0 ? "+" : ""}${pct.toFixed(2)}%</span>`;
        }

        if (priceCell && before && before !== usd(s.current_price)) {
            const went = s.current_price > parseFloat(before.replace(/[$,]/g, "")) ? "tick-up" : "tick-down";
            priceCell.classList.remove("tick-up", "tick-down");
            void priceCell.offsetWidth; // restart the flash animation
            priceCell.classList.add(went);
        }
    }

    async function refresh() {
        try {
            const response = await fetch("/api/stocks", { headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const stocks = await response.json();

            stocks.forEach((s) => {
                window.athenaPrices[s.stock_id] = s;
                document
                    .querySelectorAll(`[data-stock-id="${s.stock_id}"]`)
                    .forEach((row) => updateRow(row, s));
            });

            document.dispatchEvent(new CustomEvent("prices:update", { detail: window.athenaPrices }));
        } catch (error) {
            // Network hiccup: try again on the next interval.
        }
    }

    refresh();
    setInterval(refresh, REFRESH_MS);
})();
