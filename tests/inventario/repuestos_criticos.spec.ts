// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Inventario - Repuestos críticos', { tag: '@unitarios' }, () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Repuestos - nivel crítico en dashboard (esqueleto)', async ({ page }) => {
    // 1. Loguear como Administrador (admin1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Ir a Inventario y revisar dashboard
    await page.locator('a', { hasText: 'Inventario' }).click();
    await expect(page.locator('h1')).toBeVisible();

    // NOTE: Adjusting stock to critical requires API or direct DB manipulation; this test checks navigation.
  });
});
