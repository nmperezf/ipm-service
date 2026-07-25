// spec: testplan_operaciones_basicas.md
// seed: tests/seed.spec.ts

import { test, expect } from '@playwright/test';
import { seedDatabase } from '../helpers';

test.describe('Técnico - Enviar a revisión', () => {
  test.beforeAll(async () => {
    seedDatabase();
  });
  test('Enviar a revisión y verificar bloqueo de edición (esqueleto)', async ({ page }) => {
    // 1. Login como Técnico (tecnico1/demo123)
    await page.goto('/');
    await page.fill('input[name="username"]', 'tecnico1');
    await page.fill('input[name="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // 2. Desde la Visita completar notas_cierre y hacer 'Enviar a revisión'
    await page.locator('a', { hasText: 'Órdenes de trabajo' }).click();

    // NOTE: This test is a scaffold — requires an actual visita in a state ready to send to review.
  });
});
