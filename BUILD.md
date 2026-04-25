# Screenshot UIUX - Desktop App

MIT Licensed. Built with Electron + Playwright.

## Dev
```bash
npm install
npm start
```

## Build installers (free, unsigned)
```bash
npm run build:mac   # creates .dmg in dist/
npm run build:win   # creates .exe in dist/
```

First run will download Chromium (~170MB).

## Auto-update
Uses electron-updater with GitHub releases. Push a new tag, GitHub Actions builds and users get update automatically.

## Login storage
Auth saved for 7 days in app data folder, then auto-deleted.
