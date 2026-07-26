// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

function monthInputValueOffset(months = 0) {
  const d = new Date();
  d.setMonth(d.getMonth() + months);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  return `${y}-${m}`;
}

test.describe('Administrador - CRUD Cliente → Instalación → Contrato → Servicio', { tag: '@unitarios' }, () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Crear cliente, instalación, contrato y servicio', async ({ page }) => {
    // 1. Loguear como Administrador (admin1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Ir a Clientes → Crear nuevo Cliente
    await page.locator('a', { hasText: 'Clientes' }).first().click();
    await page.locator('a', { hasText: 'Nuevo cliente' }).click();
    await page.fill('input[name="nombre"]', 'Cliente E2E');
    await page.fill('input[name="direccion"]', 'Calle Falsa 123');
    await page.fill('input[name="contacto"]', 'Contacto');
    await page.fill('input[name="telefono"]', '12345678');
    await page.fill('input[name="email"]', 'cliente@example.test');
    await page.click('button[type="submit"]');
    await expect(page.locator('table')).toContainText('Cliente E2E');

    // 3. Abrir la ficha del Cliente y crear una Instalación
    await page.locator('a', { hasText: 'Cliente E2E' }).first().click();
    await page.locator('a', { hasText: 'Nueva instalación' }).click();
    await page.fill('input[name="nombre"]', 'Instalacion E2E');
    await page.fill('input[name="direccion"]', 'Calle Instal 45');
    await page.click('button[type="submit"]');
    await expect(page.locator('.alert.alert-success')).toContainText('Instalacion E2E');

    // 4. Dentro de la Instalación, crear un Contrato con fecha_inicio y duración 1 año
    await page.locator('div .list-group-item').first().click();
    await page.locator('a[href="/contratos/nuevo/2"]').click();
    await page.fill('input[name="nombre"]', 'Contrato E2E 2026');
    await page.fill('input[name="mes_inicio"]', monthInputValueOffset(0));
    await page.click('button[type="submit"]');
    await expect(page.locator('h1')).toContainText('Contrato E2E');

    // 5. Agregar un Servicio al Contrato con frecuencia (mensual) y fecha_inicio
    await page.fill('input[name="nombre"]', 'Servicio mensual E2E');
    await page.selectOption('select[name="frecuencia"]', 'mensual');
    await page.fill('input[name="mes_inicio"]', monthInputValueOffset(0));
    await page.click('button[type="submit"]');

    // Expected: Servicio agregado al contrato y disponible para generar visitas
    await expect(page.locator('table').first()).toContainText('Servicio mensual E2E');
  });
});
