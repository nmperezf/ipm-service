# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: inventario\repuestos_criticos.spec.ts >> Inventario - Repuestos críticos >> Repuestos - nivel crítico en dashboard (esqueleto)
- Location: tests\inventario\repuestos_criticos.spec.ts:11:7

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
  7  | test.describe('Inventario - Repuestos críticos', () => {
  8  |   test.beforeAll(async () => {
  9  |     seedDatabase();
  10 |   });
  11 |   test('Repuestos - nivel crítico en dashboard (esqueleto)', async ({ page }) => {
  12 |     // 1. Loguear como Administrador (admin1/demo123)
> 13 |     await page.goto('/');
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5000/
  14 |     await page.fill('input[name="username"]', 'admin1');
  15 |     await page.fill('input[name="password"]', 'demo123');
  16 |     await page.click('button[type="submit"]');
  17 | 
  18 |     // 2. Ir a Inventario y revisar dashboard
  19 |     await page.locator('a', { hasText: 'Inventario' }).click();
  20 |     await expect(page.locator('h1')).toBeVisible();
  21 | 
  22 |     // NOTE: Adjusting stock to critical requires API or direct DB manipulation; this test checks navigation.
  23 |   });
  24 | });
  25 | 
```