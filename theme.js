"use strict";
// Apply the saved light/dark choice before first paint (same key as the intro site).
try { const t = localStorage.getItem("vnstratlab-theme"); if (t) document.documentElement.dataset.theme = t; } catch (_) { /* storage unavailable */ }
