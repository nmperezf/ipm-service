# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tecnico\enviar_revision.spec.ts >> Técnico - Enviar a revisión >> Enviar a revisión y verificar bloqueo de edición (esqueleto)
- Location: tests\tecnico\enviar_revision.spec.ts:11:7

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
  7  | test.describe('Técnico - Enviar a revisión', () => {
  8  |   test.beforeAll(async () => {
  9  |     seedDatabase();
  10 |   });
  11 |   test('Enviar a revisión y verificar bloqueo de edición (esqueleto)', async ({ page }) => {
  12 |     // 1. Login como Técnico (tecnico1/demo123)
> 13 |     await page.goto('/');
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5000/
  14 |     await page.fill('input[name="username"]', 'tecnico1');
  15 |     await page.fill('input[name="password"]', 'demo123');
  16 |     await page.click('button[type="submit"]');
  17 | 
  18 |     // 2. Desde la Visita completar notas_cierre y hacer 'Enviar a revisión'
  19 |     await page.locator('a', { hasText: 'Órdenes de trabajo' }).click();
  20 | 
  21 |     // NOTE: This test is a scaffold — requires an actual visita in a state ready to send to review.
  22 |   });
  23 | });
  24 | 
```