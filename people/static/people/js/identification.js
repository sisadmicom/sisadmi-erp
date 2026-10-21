(() => {
    const form = document.querySelector('[data-identification-url]');
    if (!form || !form.dataset.identificationUrl) return;
    const input = form.elements.identification;
    const manual = form.elements.identification_type;
    const status = form.querySelector('[data-identification-status]');
    if (!input || !manual || !status) return;
    if (input.disabled) {
        status.textContent = "La identificación y su clasificación son inmutables.";
        return;
    }
    let timer, controller;
    const detect = () => {
        clearTimeout(timer);
        if (controller) controller.abort();
        timer = setTimeout(async () => {
            controller = new AbortController();
            try {
                const body = new URLSearchParams({identification: input.value, manual: manual.value});
                const response = await fetch(form.dataset.identificationUrl, {
                    method: 'POST', body, credentials: 'same-origin', signal: controller.signal,
                    headers: {'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}
                });
                const result = await response.json();
                status.textContent = response.ok ? `Tipo: ${result.label}. Validación estructural; no acredita registro en el SRI.` : result.error;
            } catch (error) {
                if (error.name !== 'AbortError') status.textContent = 'No se pudo detectar el tipo. Se validará al guardar.';
            }
        }, 250);
    };
    input.addEventListener('input', detect);
    manual.addEventListener('change', detect);
})();
