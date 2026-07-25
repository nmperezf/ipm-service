# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: admin\crud_cliente_contrato.spec.ts >> Administrador - CRUD Cliente → Instalación → Contrato → Servicio >> Crear cliente, instalación, contrato y servicio
- Location: tests\admin\crud_cliente_contrato.spec.ts:19:7

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h1')
Expected substring: "Instalacion E2E"
Received string:    "Cliente E2E"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h1')
    14 × locator resolved to <h1>Cliente E2E</h1>
       - unexpected value "Cliente E2E"

```

```yaml
- heading "Cliente E2E" [level=1]
```

# Test source

```ts
  1  | // spec: testplan_operaciones_basicas.md
  2  | // seed: tests/seed.spec.ts
  3  | 
  4  | import { test, expect } from '@playwright/test';
  5  | import { seedDatabase } from '../helpers';
  6  | 
  7  | function monthInputValueOffset(months = 0) {
  8  |   const d = new Date();
  9  |   d.setMonth(d.getMonth() + months);
  10 |   const y = d.getFullYear();
  11 |   const m = String(d.getMonth() + 1).padStart(2, '0');
  12 |   return `${y}-${m}`;
  13 | }
  14 | 
  15 | test.describe('Administrador - CRUD Cliente → Instalación → Contrato → Servicio', () => {
  16 |   test.beforeAll(async () => {
  17 |     seedDatabase();
  18 |   });
  19 |   test('Crear cliente, instalación, contrato y servicio', async ({ page }) => {
  20 |     // 1. Loguear como Administrador (admin1/demo123)
  21 |     await page.goto('/');
  22 |     await page.fill('input[name="username"]', 'admin1');
  23 |     await page.fill('input[name="password"]', 'demo123');
  24 |     await page.click('button[type="submit"]');
  25 | 
  26 |     // 2. Ir a Clientes → Crear nuevo Cliente
  27 |     await page.locator('a', { hasText: 'Clientes' }).first().click();
  28 |     await page.locator('a', { hasText: 'Nuevo cliente' }).click();
  29 |     await page.fill('input[name="nombre"]', 'Cliente E2E');
  30 |     await page.fill('input[name="direccion"]', 'Calle Falsa 123');
  31 |     await page.fill('input[name="contacto"]', 'Contacto');
  32 |     await page.fill('input[name="telefono"]', '12345678');
  33 |     await page.fill('input[name="email"]', 'cliente@example.test');
  34 |     await page.click('button[type="submit"]');
  35 |     await expect(page.locator('table')).toContainText('Cliente E2E');
  36 | 
  37 |     // 3. Abrir la ficha del Cliente y crear una Instalación
  38 |     await page.locator('a', { hasText: 'Cliente E2E' }).click();
  39 |     await page.locator('a', { hasText: 'Nueva instalación' }).click();
  40 |     await page.fill('input[name="nombre"]', 'Instalacion E2E');
  41 |     await page.fill('input[name="direccion"]', 'Calle Instal 45');
  42 |     await page.click('button[type="submit"]');
> 43 |     await expect(page.locator('h1')).toContainText('Instalacion E2E');
     |                                      ^ Error: expect(locator).toContainText(expected) failed
  44 | 
  45 |     // 4. Dentro de la Instalación, crear un Contrato con fecha_inicio y duración 1 año
  46 |     await page.locator('a', { hasText: 'Nuevo contrato' }).click();
  47 |     await page.fill('input[name="nombre"]', 'Contrato E2E 2026');
  48 |     await page.fill('input[name="mes_inicio"]', monthInputValueOffset(0));
  49 |     await page.click('button[type="submit"]');
  50 |     await expect(page.locator('h1')).toContainText('Contrato E2E');
  51 | 
  52 |     // 5. Agregar un Servicio al Contrato con frecuencia (mensual) y fecha_inicio
  53 |     await page.fill('input[name="nombre"]', 'Servicio mensual E2E');
  54 |     await page.selectOption('select[name="frecuencia"]', 'mensual');
  55 |     await page.fill('input[name="mes_inicio"]', monthInputValueOffset(0));
  56 |     await page.click('button[type="submit"]');
  57 | 
  58 |     // Expected: Servicio agregado al contrato y disponible para generar visitas
  59 |     await expect(page.locator('table')).toContainText('Servicio mensual E2E');
  60 |   });
  61 | });
  62 | 
```