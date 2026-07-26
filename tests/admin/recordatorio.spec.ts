
import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Inventario - Recordatorios', { tag: '@unitarios' }, () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  
  test('Ver Recordatorios (esqueleto)', async ({ page }) => {
    // 1. Loguear como Administrador (admin1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Ver los Recordatorios
    await expect(page.getByRole('heading', { name: 'Recordatorios' })).toBeVisible();

    //3. Ver los campos del formulario de recordatorio
    await expect(page.getByRole('textbox', { name: 'Ej: Llamar a fulano por' }), "Campo ejemplo input recordatorio no visible").toBeVisible();
    await expect(page.locator('select[name="cliente_id"]'), "Selecion de cliente no visible").toBeVisible();
    await expect(page.locator('select[name="prioridad"]'), "Seleccion de prioridad no visible").toBeVisible();
    await expect(page.getByRole('button', { name: 'Agregar' }), "Boton AGREGAR no visible").toBeVisible();
  });
});