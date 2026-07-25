# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: admin\dashboard.spec.ts >> Administrador / Jefe >> Login y Dashboard operativo
- Location: tests\admin\dashboard.spec.ts:11:7

# Error details

```
Error: expect(locator).toHaveText(expected) failed

Locator: locator('h1')
Expected pattern: /Inicio|Dashboard/
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toHaveText" with timeout 5000ms
  - waiting for locator('h1')

```

```yaml
- navigation:
  - link "IPM Service":
    - /url: /
  - list:
    - listitem:
      - link "Inicio":
        - /url: /
    - listitem:
      - link "Clientes":
        - /url: /clientes/
    - listitem:
      - link "Calendario":
        - /url: /planificacion/calendario
    - listitem:
      - link "Órdenes de trabajo":
        - /url: /ordenes-trabajo/
    - listitem:
      - link "Inventario":
        - /url: /inventario/
    - listitem:
      - link "Usuarios":
        - /url: /usuarios/
  - list:
    - listitem: Nicolás (Administrador) (Administrador)
    - listitem:
      - link "Cerrar sesión":
        - /url: /logout
- alert:
  - text: Bienvenido, Nicolás (Administrador).
  - button
- textbox "Buscar cliente por nombre..."
- button "Buscar"
- link "0 Clientes con críticas abiertas":
  - /url: /clientes-con-novedad/Deficiencia%20cr%C3%ADtica
- link "1 Clientes con no críticas abiertas":
  - /url: /clientes-con-novedad/Deficiencia%20no%20cr%C3%ADtica
- link "0 Clientes con desactivaciones":
  - /url: /clientes-con-novedad/Desactivaci%C3%B3n
- link "0 Clientes con comentarios":
  - /url: /clientes-con-novedad/Comentario
- link "4 Visitas vencidas":
  - /url: /visitas-vencidas
- link "0 Visitas en revisión":
  - /url: /visitas-en-revision
- link "9 OT pendientes":
  - /url: /ordenes-trabajo/
- link "1 Repuestos en nivel crítico":
  - /url: /inventario/criticos
- link "100.0% Cumplimiento de July 2026 (2/2 servicios)":
  - /url: /cumplimiento-mensual
- heading "Agenda de esta semana" [level=4]
- table:
  - rowgroup:
    - row "Fecha Cliente Instalación Estado":
      - columnheader "Fecha"
      - columnheader "Cliente"
      - columnheader "Instalación"
      - columnheader "Estado"
    - row:
      - columnheader:
        - textbox "Filtrar…"
      - columnheader:
        - textbox "Filtrar…"
      - columnheader:
        - textbox "Filtrar…"
      - columnheader:
        - textbox "Filtrar…"
  - rowgroup:
    - row "27/07 Shopping Costa Azul Edificio Central Realizado":
      - cell "27/07"
      - cell "Shopping Costa Azul":
        - link "Shopping Costa Azul":
          - /url: /clientes/1
      - cell "Edificio Central"
      - cell "Realizado":
        - link "Realizado":
          - /url: /visitas/5
    - row "27/07 Shopping Costa Azul Edificio Central Realizado":
      - cell "27/07"
      - cell "Shopping Costa Azul":
        - link "Shopping Costa Azul":
          - /url: /clientes/1
      - cell "Edificio Central"
      - cell "Realizado":
        - link "Realizado":
          - /url: /visitas/10
- heading "Recordatorios" [level=4]
- 'textbox "Ej: Llamar a fulano por renovación de contrato"'
- combobox:
  - option "-- Sin cliente asociado --" [selected]
  - option "Shopping Costa Azul"
- combobox:
  - option "Baja"
  - option "Media" [selected]
  - option "Alta"
  - option "Urgente"
- button "Agregar"
- text: Urgente Coordinar con el cliente la renovación del contrato antes de marzo —
- link "Shopping Costa Azul":
  - /url: /clientes/1
- text: (25/07/2026)
- button "Resuelto"
- button "Eliminar"
```

# Test source

```ts
  1  | // spec: testplan_operaciones_basicas.md
  2  | // seed: tests/seed.spec.ts
  3  | 
  4  | import { test, expect } from '@playwright/test';
  5  | import { seedDatabase } from '../helpers';
  6  | 
  7  | test.describe('Administrador / Jefe', () => {
  8  |   test.beforeAll(async () => {
  9  |     seedDatabase();
  10 |   });
  11 |   test('Login y Dashboard operativo', async ({ page }) => {
  12 |     // 1. Abrir app y loguear como Administrador (admin1/demo123)
  13 |     await page.goto('/');
  14 |     await page.fill('input[name="username"]', 'admin1');
  15 |     await page.fill('input[name="password"]', 'demo123');
  16 |     await page.click('button[type="submit"]');
  17 | 
  18 |     // 2. Abrir Dashboard operativo
> 19 |     await expect(page.locator('h1')).toHaveText(/Inicio|Dashboard/);
     |                                      ^ Error: expect(locator).toHaveText(expected) failed
  20 |     // Check for search input as indicator of dashboard
  21 |     await expect(page.locator('input[name="q"]')).toBeVisible();
  22 |   });
  23 | });
  24 | 
```