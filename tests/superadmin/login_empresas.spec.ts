// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Super Admin', () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Login y navegación a Empresas', async ({ page }) => {
    // 1. Abrir la aplicación en http://localhost:5000
    await page.goto('/');

    // 2. Ingresar credenciales de Super Admin (usar admin/admin123 por defecto)
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');

    // 3. Enviar formulario de login
    await page.click('button[type="submit"]');

    // Esperar que la navegación a dashboard ocurra y que el enlace Empresas esté visible
    const empresasLink = page.locator('a', { hasText: 'Empresas' });
    await expect(empresasLink).toBeVisible();

    // 4. Desde la pantalla inicial, abrir la sección "Empresas"
    await empresasLink.click();

    // Expected: Listado de empresas visible, botón "Crear Empresa" presente
    await expect(page.locator('h1')).toHaveText('Empresas');
    const nueva1 = await page.locator('a', { hasText: 'Nueva empresa' }).first().isVisible();
    const nueva2 = await page.locator('a', { hasText: '+ Nueva empresa' }).first().isVisible();
    expect(nueva1 || nueva2).toBeTruthy();
  });
});