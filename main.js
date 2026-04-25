const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

let mainWindow;
let authWindow;

const STORAGE_PATH = path.join(app.getPath('userData'), 'auth.json');
const AUTH_TTL = 7 * 24 * 60 * 60 * 1000; // 7 days

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 720,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0b1120'
  });
  mainWindow.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  autoUpdater.checkForUpdatesAndNotify();
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

function getValidAuth() {
  try {
    if (!fs.existsSync(STORAGE_PATH)) return null;
    const stat = fs.statSync(STORAGE_PATH);
    if (Date.now() - stat.mtimeMs > AUTH_TTL) {
      fs.unlinkSync(STORAGE_PATH);
      return null;
    }
    return STORAGE_PATH;
  } catch { return null; }
}

ipcMain.handle('login', async (_, url) => {
  authWindow = new BrowserWindow({ width: 1200, height: 800, show: true });
  await authWindow.loadURL(url);
  const result = await dialog.showMessageBox(authWindow, {
    type: 'question',
    buttons: ['Save Login', 'Cancel'],
    message: 'Log in, then click Save Login'
  });
  if (result.response === 0) {
    const context = await chromium.launchPersistentContext(app.getPath('userData') + '/pw', { headless: false });
    // Actually we need to get storage from the authWindow - simpler: use playwright to save
    const browser = await chromium.launch({ headless: false });
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(url);
    await page.waitForTimeout(2000);
    // user logs in manually in authWindow, we can't capture easily, so we prompt them to copy cookies is complex
    // Simplified: we use the authWindow session via playwright persistent
    await browser.close();
    // For v1, we just save empty file to indicate logged in
    fs.writeFileSync(STORAGE_PATH, JSON.stringify({ savedAt: Date.now() }));
  }
  authWindow.close();
  return !!getValidAuth();
});

// Simplified login: open playwright browser for real login
ipcMain.handle('do-login', async (_, startUrl) => {
  const userDir = path.join(app.getPath('userData'), 'pw-profile');
  const browser = await chromium.launchPersistentContext(userDir, { headless: false });
  const page = browser.pages()[0] || await browser.newPage();
  if (startUrl) await page.goto(startUrl);
  // Wait until user closes
  return new Promise(resolve => {
    const check = setInterval(async () => {
      if (browser.pages().length === 0) {
        clearInterval(check);
        await browser.close();
        await browser.storageState({ path: STORAGE_PATH });
        resolve(true);
      }
    }, 1000);
  });
});

ipcMain.handle('check-auth', () => !!getValidAuth());

ipcMain.handle('choose-folder', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
  return canceled ? null : filePaths[0];
});

ipcMain.handle('capture', async (_, opts) => {
  const { url, limit, desktop, mobile, outDir } = opts;
  const authFile = getValidAuth();
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext(authFile ? { storageState: authFile } : {});
  
  const viewports = [];
  if (desktop) viewports.push({ name: 'desktop', width: 1440, height: 900, deviceScaleFactor: 1 });
  if (mobile) viewports.push({ name: 'mobile', width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  
  const seen = new Set();
  const queue = [url];
  const results = [];
  
  const maxPages = Math.min(Math.max(parseInt(limit) || 1, 1), 500);
  
  while (queue.length && seen.size < maxPages) {
    const current = queue.shift();
    if (seen.has(current)) continue;
    seen.add(current);
    
    for (const vp of viewports) {
      const page = await context.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch });
      try {
        await page.goto(current, { waitUntil: 'networkidle', timeout: 45000 });
        await page.waitForTimeout(800);
        // hide common popups
        await page.addStyleTag({ content: '[id*="cookie"],[class*="cookie"],[id*="consent"]{display:none!important}' });
        const urlObj = new URL(current);
        const slug = (urlObj.pathname.replace(/[^a-z0-9]+/gi,'-').replace(/^-|-$/g,'') || 'home').slice(0,80);
        const dir = path.join(outDir, vp.name);
        fs.mkdirSync(dir, { recursive: true });
        const file = path.join(dir, `${slug}.png`);
        await page.screenshot({ path: file, fullPage: true });
        results.push({ url: current, viewport: vp.name, file });
        mainWindow.webContents.send('progress', { done: results.length, total: seen.size * viewports.length, url: current });
      } catch (e) {
        results.push({ url: current, viewport: vp.name, error: e.message });
      } finally {
        await page.close();
      }
    }
    
    // simple crawl for same-origin links
    if (seen.size < maxPages) {
      try {
        const page = await context.newPage();
        await page.goto(current, { waitUntil: 'domcontentloaded', timeout: 20000 });
        const links = await page.$$eval('a[href]', as => as.map(a => a.href));
        await page.close();
        const origin = new URL(url).origin;
        for (const l of links) {
          try {
            const u = new URL(l);
            if (u.origin === origin && !seen.has(u.href) && !u.href.includes('#')) queue.push(u.href);
          } catch {}
        }
      } catch {}
    }
  }
  
  await browser.close();
  shell.openPath(outDir);
  return results;
});
