# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: superadmin\login_empresas.spec.ts >> Super Admin >> Login y navegación a Empresas
- Location: tests\superadmin\login_empresas.spec.ts:11:7

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5000/
Call log:
  - navigating to "http://localhost:5000/", waiting until "load"

```

# Test source

```ts
  1  | // spec: testplan_operaciones_basicas.md
  2  | // seed: tests/seed.spec.ts
  3  | 
  4  | import { test, expect } from '@playwright/test';
  5  | import { seedDatabase } from '../helpers';
  6  | 
  7  | test.describe('Super Admin', () => {
  8  |   test.beforeAll(async () => {
  9  |     seedDatabase();
  10 |   });
  11 |   test('Login y navegación a Empresas', async ({ page }) => {
  12 |     // 1. Abrir la aplicación en http://localhost:5000
> 13 |     await page.goto('/');
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5000/
  14 | 
  15 |     // 2. Ingresar credenciales de Super Admin (usar admin/admin123 por defecto)
  16 |     await page.fill('input[name="username"]', 'admin');
  17 |     await page.fill('input[name="password"]', 'admin123');
  18 | 
  19 |     // 3. Enviar formulario de login
  20 |     await page.click('button[type="submit"]');
  21 | 
  22 |     // Esperar que la navegación a dashboard ocurra y que el enlace Empresas esté visible
  23 |     const empresasLink = page.locator('a', { hasText: 'Empresas' });
  24 |     await expect(empresasLink).toBeVisible();
  25 | 
  26 |     // 4. Desde la pantalla inicial, abrir la sección "Empresas"
  27 |     await empresasLink.click();
  28 | 
  29 |     // Expected: Listado de empresas visible, botón "Crear Empresa" presente
  30 |     await expect(page.locator('h1')).toHaveText('Empresas');
  31 |     const nueva1 = await page.locator('a', { hasText: 'Nueva empresa' }).first().isVisible();
  32 |     const nueva2 = await page.locator('a', { hasText: '+ Nueva empresa' }).first().isVisible();
  33 |     expect(nueva1 || nueva2).toBeTruthy();
  34 |   });
  35 | });
```