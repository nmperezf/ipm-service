// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Técnico', { tag: '@unitarios' }, () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Login y ver mis OT asignadas', async ({ page }) => {
    // 1. Login como Técnico (tecnico1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'tecnico1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Abrir sección Órdenes de Trabajo y filtrar por 'Mis OT'
    await page.locator('a', { hasText: 'Órdenes de trabajo' }).click();
    // Assert that the orders table loads
    await expect(page.locator('table')).toBeVisible();
  });
});
