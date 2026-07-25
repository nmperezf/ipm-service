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

    // --- Fila de filtros, una casilla por columna ---
    const filaFiltros = document.createElement('tr');
    filaFiltros.className = 'tabla-filtros';
    columnas.forEach(function () {
        const celda = document.createElement('th');
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.setAttribute('placeholder', 'Filtrar…');
        input.addEventListener('input', function () { aplicarFiltros(tabla); });
        celda.appendChild(input);
        filaFiltros.appendChild(celda);
    });
    thead.appendChild(filaFiltros);

    // --- Encabezados clickeables para ordenar ---
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

function aplicarFiltros(tabla) {
    const filaFiltros = tabla.tHead.querySelector('.tabla-filtros');
    const valores = Array.from(filaFiltros.cells).map(function (td) {
        return td.querySelector('input').value.trim().toLowerCase();
    });
    const tbody = tabla.tBodies[0];

    Array.from(tbody.rows).forEach(function (fila) {
        let visible = true;
        valores.forEach(function (valor, indice) {
            if (!valor) return;
            const celda = fila.cells[indice];
            const texto = celda ? celda.textContent.toLowerCase() : '';
            if (!texto.includes(valor)) visible = false;
        });
        fila.style.display = visible ? '' : 'none';
    });
}
