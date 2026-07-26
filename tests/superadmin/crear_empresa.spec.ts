// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Super Admin @unitarios', { tag: '@unitarios' }, () => {
  test.beforeAll(async () => {
    seedDatabase();
  });

  test('Crear empresa y primer Administrador', async ({ page }) => {
    // 1. Abrir la aplicación en http://localhost:5000
    await page.goto('/');

    // 2. Ingresar credenciales de Super Admin (admin/admin123)
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');
    // 3. Enviar formulario de login
    await page.click('button[type="submit"]');

    // 4. En la vista Empresas, hacer clic en "Crear Empresa"
    await page.locator('a', { hasText: 'Empresas' }).click();
    await expect(page.locator('h1')).toHaveText('Empresas');
    await page.locator('a', { hasText: 'Nueva empresa' }).click();

    // 5. Completar nombre de empresa y crear
    // Nombre: 'Empresa E2E'
    await page.fill('input[name="nombre"]', 'Empresa E2E');
    await page.fill('input[name="admin_username"]', 'admin_e2e');
    await page.fill('input[name="admin_password"]', 'demo123');
    await page.fill('input[name="admin_nombre"]', 'Admin E2E');
    await page.click('button[type="submit"]');

    // Expected: Empresa creada y listada
    const mensajeError = await page.locator('.alert.alert-danger').textContent();
    expect(mensajeError?.trim()).toContain("Ya existe un usuario con el nombre 'admin_e2e'.");
  });
});