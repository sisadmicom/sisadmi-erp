(() => {
    document.querySelectorAll("[data-form-ux]").forEach((root) => {
        if (root.dataset.helpEnhanced === "true") return;
        const panel = root.querySelector("[data-contextual-help]");
        if (!panel || !root.querySelector("[data-help-for]")) return;
        const title = panel.querySelector("[data-contextual-help-title]");
        const text = panel.querySelector("[data-contextual-help-text]");

        const updateHelp = (target) => {
            if (!target.matches("input, select, textarea")) return;
            const field = target.closest("[data-form-field]");
            if (!field || !root.contains(field)) return;
            const help = field.querySelector("[data-help-for]");
            title.textContent = field.dataset.helpTitle;
            text.textContent = help ? help.textContent.trim() : "Este campo no tiene ayuda adicional.";
        };

        root.addEventListener("focusin", (event) => updateHelp(event.target));
        root.dataset.helpEnhanced = "true";
        panel.hidden = false;
        if (root.contains(document.activeElement)) updateHelp(document.activeElement);
    });
})();
