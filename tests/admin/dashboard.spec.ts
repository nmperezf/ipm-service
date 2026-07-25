// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Administrador / Jefe', () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Login y Dashboard operativo', async ({ page }) => {
    // 1. Abrir app y loguear como Administrador (admin1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Abrir Dashboard operativo
    await expect(page.locator('h1')).toHaveText(/Inicio|Dashboard/);
    // Check for search input as indicator of dashboard
    await expect(page.locator('input[name="q"]')).toBeVisible();
  });
});
