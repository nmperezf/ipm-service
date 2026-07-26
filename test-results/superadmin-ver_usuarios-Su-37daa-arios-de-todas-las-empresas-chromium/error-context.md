# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: superadmin\ver_usuarios.spec.ts >> Super Admin >> Ver usuarios de todas las empresas
- Location: tests\superadmin\ver_usuarios.spec.ts:11:7

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
  11 |   test('Ver usuarios de todas las empresas', async ({ page }) => {
  12 |     // 1. Abrir la aplicación y loguear como Super Admin
> 13 |     await page.goto('/');
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5000/
  14 |     await page.fill('input[name="username"]', 'admin');
  15 |     await page.fill('input[name="password"]', 'admin123');
  16 |     await page.click('button[type="submit"]');
  17 | 
  18 |     // 2. Ingresar a la sección "Usuarios" como Super Admin
  19 |     await page.locator('a', { hasText: 'Usuarios' }).click();
  20 |     await expect(page.locator('h1')).toHaveText('Usuarios');
  21 | 
  22 |     // 3. Buscar usuarios por empresa y por username (usa la búsqueda de la tabla si existe)
  23 |     // Asserting that the users table lists at least one username (admin)
  24 |     await expect(page.locator('table')).toContainText('admin');
  25 |   });
  26 | });
  27 | 
```