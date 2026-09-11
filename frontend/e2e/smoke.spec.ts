import { test, expect } from '@playwright/test';

// Flujo crítico: login → dashboard. El backend se mockea a nivel de red.
test.describe('MAPUS smoke', () => {
  test('login muestra formulario y enlace de recuperación', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h2', { hasText: 'Iniciar Sesión' })).toBeVisible();
    await expect(page.locator('text=¿Olvidaste tu contraseña?')).toBeVisible();
  });

  test('ruta protegida redirige a login sin sesión', async ({ page }) => {
    await page.goto('/dashboard-apus');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('login exitoso navega al dashboard', async ({ page }) => {
    // JWT sin firmar pero con exp futuro: el AuthGuard solo lee el payload.
    const payload = Buffer.from(
      JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }),
    ).toString('base64');
    await page.route('**/api/v1/auth/login', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: `x.${payload}.y`,
          refresh_token: 'fake-refresh',
          token_type: 'bearer',
          user: { id: 1, nombre: 'Test', rol: 'admin', telefono: '3000000001' },
        }),
      });
    });
    await page.route('**/api/v1/dashboard**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.goto('/login');
    await page.fill('#username', '3000000001');
    await page.fill('#password', 'Clave2026');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/dashboard-apus$/, { timeout: 15000 });
  });

  test('recuperación: generar token y restablecer', async ({ page }) => {
    await page.route('**/api/v1/auth/forgot-password', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, mensaje: 'ok', reset_token: 'TOKEN123' }),
      });
    });
    await page.route('**/api/v1/auth/reset-password', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, mensaje: 'ok' }),
      });
    });
    await page.goto('/login');
    await page.click('text=¿Olvidaste tu contraseña?');
    await page.fill('#identificador', '3000000001');
    await page.click('button[type="submit"]');
    await expect(page.locator('#reset-token')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#reset-token')).toHaveValue('TOKEN123');
    await page.fill('#nueva-password', 'Nueva2026');
    await page.click('button[type="submit"]');
    await expect(page.locator('h2', { hasText: 'Iniciar Sesión' })).toBeVisible({ timeout: 10000 });
  });
});
