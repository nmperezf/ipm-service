/*
 * Ordenamiento y filtrado por columna para cualquier tabla marcada con
 * class="data-table". No requiere tocar cada página: alcanza con esa
 * clase en el <table>. Funciona sobre tablas con <thead>/<tbody>.
 */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table.data-table').forEach(initTabla);
});

function initTabla(tabla) {
    const thead = tabla.tHead;
    const tbody = tabla.tBodies[0];
    if (!thead || !tbody) return;

    const filasEncabezado = thead.rows;
    const filaTitulos = filasEncabezado[filasEncabezado.length - 1];
    const columnas = Array.from(filaTitulos.cells);

    // No tiene sentido ordenar/filtrar una tabla sin filas de datos reales
    if (tbody.rows.length === 0 || (tbody.rows.length === 1 && tbody.rows[0].cells.length === 1)) {
        return;
    }

    // --- Buscador único: filtra por el texto completo de la fila ---
    // (si la página ya trae su propio buscador+chips para esta tabla,
    // marcada con data-buscador-propio, no se duplica; tampoco vale la
    // pena mostrarlo sobre tablas con pocas filas, como cada mes de la
    // hoja de ruta)
    if (!('buscadorPropio' in tabla.dataset) && tbody.rows.length > 5) {
        const buscador = document.createElement('div');
        buscador.className = 'buscador-doc buscador-tabla-doc';
        buscador.innerHTML =
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
            '<input type="text" placeholder="Buscar…">';
        buscador.querySelector('input').addEventListener('input', function (ev) {
            aplicarFiltro(tabla, ev.target.value);
        });
        const contenedor = tabla.closest('.table-responsive') || tabla;
        contenedor.parentNode.insertBefore(buscador, contenedor);
    }

    // --- Encabezados clickeables para ordenar ---
    // (si la página ya resuelve el orden por columna del lado del
    // servidor —paginación real, ver app/templates/_paginacion.html—,
    // marcada con data-orden-propio, no se pisa con este sort client-side)
    if (!('ordenPropio' in tabla.dataset)) {
        columnas.forEach(function (th, indice) {
            th.classList.add('th-ordenable');
            th.dataset.dir = '';
            const indicador = document.createElement('span');
            indicador.className = 'indicador-orden';
            th.appendChild(indicador);
            th.addEventListener('click', function () {
                ordenarPorColumna(tabla, indice, th);
            });
        });
    }

    // --- Filas clickeables (<tr data-href="...">), sin interferir con
    // los links/botones/forms que ya haya adentro de la fila ---
    Array.from(tbody.rows).forEach(function (fila) {
        if (!fila.dataset.href) return;
        fila.classList.add('fila-clickeable');
        fila.addEventListener('click', function (ev) {
            if (ev.target.closest('a, button, form, input, select, textarea')) return;
            window.location = fila.dataset.href;
        });
    });
}

function ordenarPorColumna(tabla, indiceColumna, th) {
    const tbody = tabla.tBodies[0];
    const filas = Array.from(tbody.rows);
    const nuevaDireccion = th.dataset.dir === 'asc' ? 'desc' : 'asc';

    // Resetea el indicador de las demás columnas de esta tabla
    const filaTitulos = tabla.tHead.rows[0];
    Array.from(filaTitulos.cells).forEach(function (h) {
        h.dataset.dir = '';
        const ind = h.querySelector('.indicador-orden');
        if (ind) ind.textContent = '';
    });
    th.dataset.dir = nuevaDireccion;
    const indicador = th.querySelector('.indicador-orden');
    if (indicador) indicador.textContent = nuevaDireccion === 'asc' ? ' \u25B2' : ' \u25BC';

    filas.sort(function (filaA, filaB) {
        const a = valorCelda(filaA.cells[indiceColumna]);
        const b = valorCelda(filaB.cells[indiceColumna]);
        let comparacion;
        if (a.numero !== null && b.numero !== null) {
            comparacion = a.numero - b.numero;
        } else {
            comparacion = a.texto.localeCompare(b.texto, 'es', { sensitivity: 'base' });
        }
        return nuevaDireccion === 'asc' ? comparacion : -comparacion;
    });

    filas.forEach(function (fila) { tbody.appendChild(fila); });
}

function valorCelda(celda) {
    if (!celda) return { texto: '', numero: null };
    const texto = celda.textContent.trim();

    // Fecha dd/mm/yyyy (con hora opcional) -> ordenable como yyyymmdd
    const fecha = texto.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
    if (fecha) {
        const dia = fecha[1], mes = fecha[2], anio = fecha[3];
        return { texto: texto.toLowerCase(), numero: parseInt(anio + mes + dia, 10) };
    }

    // Número al inicio de la celda (ej: "42", "3.5", "12 unidad", "87%")
    const numeroMatch = texto.replace(',', '.').match(/^-?\d+(\.\d+)?/);
    if (numeroMatch) {
        return { texto: texto.toLowerCase(), numero: parseFloat(numeroMatch[0]) };
    }

    return { texto: texto.toLowerCase(), numero: null };
}

function aplicarFiltro(tabla, valor) {
    const busqueda = valor.trim().toLowerCase();
    const tbody = tabla.tBodies[0];
    Array.from(tbody.rows).forEach(function (fila) {
        const texto = fila.textContent.toLowerCase();
        fila.style.display = !busqueda || texto.includes(busqueda) ? '' : 'none';
    });
}
