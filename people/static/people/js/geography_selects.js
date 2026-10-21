// Progressive enhancement only: the native refresh button works without JS.
(() => {
    const form = document.querySelector("[data-person-form]");
    if (!form) return;
    const chain = ["continent", "country", "province", "canton", "parish"];
    const button = form.querySelector("[data-refresh-geography]");
    form.addEventListener("change", (event) => {
        const index = chain.indexOf(event.target.name);
        if (index < 0 || index === chain.length - 1) return;
        chain.slice(index + 1).forEach((name) => { form.elements[name].value = ""; });
        if (form.requestSubmit) form.requestSubmit(button);
    });
})();
