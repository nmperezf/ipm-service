// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Super Admin', () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Ver usuarios de todas las empresas', async ({ page }) => {
    // 1. Abrir la aplicación y loguear como Super Admin
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // 2. Ingresar a la sección "Usuarios" como Super Admin
    await page.locator('a', { hasText: 'Usuarios' }).click();
    await expect(page.locator('h1')).toHaveText('Usuarios');

    // 3. Buscar usuarios por empresa y por username (usa la búsqueda de la tabla si existe)
    // Asserting that the users table lists at least one username (admin)
    await expect(page.locator('table')).toContainText('admin');
  });
});
