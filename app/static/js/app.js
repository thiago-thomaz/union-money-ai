/**
 * UNION MONEY AI - Utilitários mínimos de interface (Vanilla JS)
 */
async function postJson(url, data, method = "POST") {
    const response = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: data ? JSON.stringify(data) : undefined,
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.detail || "Erro ao processar requisição.");
    }
    return payload;
}

async function generatePdfReport() {
    try {
        const res = await postJson("/api/dashboard/report-pdf", {});
        alert("Relatório PDF gerado com sucesso em: " + res.file_path);
    } catch (err) {
        alert("Erro ao gerar PDF: " + err.message);
    }
}

async function deleteProductById(productId) {
    if (!confirm("Deseja desativar este produto?")) return;
    try {
        await postJson(`/api/products/${productId}`, null, "DELETE");
        window.location.reload();
    } catch (err) {
        alert("Erro: " + err.message);
    }
}

