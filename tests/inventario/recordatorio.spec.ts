
import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Inventario - Recordatorios', () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Crear y resolver Recordatorio (esqueleto)', async ({ page }) => {
    // 1. Loguear como Administrador (admin1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Crear un Recordatorio asociado a un Cliente
    await expect(page.locator('a', { hasText: 'Recordatorios' }), "Recordatorios link no visible").toBeVisible();
    await page.locator('a', { hasText: 'Recordatorios' }).click();
  });
});