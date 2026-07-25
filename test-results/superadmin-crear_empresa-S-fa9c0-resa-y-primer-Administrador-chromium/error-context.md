# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: superadmin\crear_empresa.spec.ts >> Super Admin >> Crear empresa y primer Administrador
- Location: tests\superadmin\crear_empresa.spec.ts:11:7

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('table')
Expected substring: "Empresa E2E"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('table')

```

```yaml
- navigation:
  - link "IPM Service":
    - /url: /
  - list:
    - listitem:
      - link "Inicio":
        - /url: /
    - listitem:
      - link "Usuarios":
        - /url: /usuarios/
    - listitem:
      - link "Empresas":
        - /url: /empresas/
  - list:
    - listitem: Super Administrador (Super Admin)
    - listitem:
      - link "Cerrar sesión":
        - /url: /logout
- alert:
  - text: Ya existe un usuario con el nombre 'admin_e2e'.
  - button
- heading "Nueva empresa" [level=1]
- paragraph: Se crea la empresa junto con su primer usuario Administrador. De ahí en más, ese Administrador gestiona el resto de sus usuarios (técnicos y clientes).
- text: Nombre de la empresa
- textbox
- separator
- heading "Primer usuario administrador" [level=5]
- text: Nombre completo
- textbox
- text: Usuario
- textbox
- text: Contraseña
- textbox
- button "Crear empresa"
- link "Cancelar":
  - /url: /empresas/
```

# Test source

```ts
  1  | // spec: testplan_operaciones_basicas.md
  2  | // seed: tests/seed.spec.ts
  3  | 
  4  | import { test, expect } from '@playwright/test';
  5  | import { seedDatabase } from '../helpers';
  6  | 
  7  | test.describe('Super Admin', () => {
  8  |   test.beforeAll(async () => {
  9  |     seedDatabase();
  10 |   });
  11 |   test('Crear empresa y primer Administrador', async ({ page }) => {
  12 |     // 1. Abrir la aplicación en http://localhost:5000
  13 |     await page.goto('/');
  14 | 
  15 |     // 2. Ingresar credenciales de Super Admin (admin/admin123)
  16 |     await page.fill('input[name="username"]', 'admin');
  17 |     await page.fill('input[name="password"]', 'admin123');
  18 |     // 3. Enviar formulario de login
  19 |     await page.click('button[type="submit"]');
  20 | 
  21 |     // 4. En la vista Empresas, hacer clic en "Crear Empresa"
  22 |     await page.locator('a', { hasText: 'Empresas' }).click();
  23 |     await expect(page.locator('h1')).toHaveText('Empresas');
  24 |     await page.locator('a', { hasText: 'Nueva empresa' }).click();
  25 | 
  26 |     // 5. Completar nombre de empresa y crear
  27 |     // Nombre: 'Empresa E2E'
  28 |     await page.fill('input[name="nombre"]', 'Empresa E2E');
  29 |     await page.fill('input[name="admin_username"]', 'admin_e2e');
  30 |     await page.fill('input[name="admin_password"]', 'demo123');
  31 |     await page.fill('input[name="admin_nombre"]', 'Admin E2E');
  32 |     await page.click('button[type="submit"]');
  33 | 
  34 |     // Expected: Empresa creada y listada
> 35 |     await expect(page.locator('table')).toContainText('Empresa E2E');
     |                                         ^ Error: expect(locator).toContainText(expected) failed
  36 | 
  37 |     // 6. Abrir la ficha de la nueva empresa y crear un usuario Administrador
  38 |     await page.locator('a', { hasText: 'Editar' }).click();
  39 |     // The edit page allows updating; the creation already created the first admin.
  40 |   });
  41 | });
  42 | 
```