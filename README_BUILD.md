# TNE Case Packaging Kit

This kit assumes the main Streamlit app is `optimize/Total.py`.

## Why this works

PyInstaller often struggles with large Streamlit apps because of hidden imports.  
So we package the whole `optimize/` folder as source into `dist/TNECase/app/` and build only a small launcher executable.

## Windows build

Run from repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Output:

- `dist\TNECase\TNECase.exe`
- Logs: `%APPDATA%\TGECase\tgecase.log`
- Crash reports: `%APPDATA%\TGECase\reports\`

Optional remote error reporting:

- `TGECASE_ERROR_REPORT_URL=https://your-endpoint`
- `TGECASE_ERROR_REPORT_TOKEN=...`
- `TGECASE_ERROR_REPORT_SECRET=...`

If `TGECASE_ERROR_REPORT_URL` is not set, the app still saves full local JSON crash reports.

## GitHub Actions build

Copy `build.yml` into `.github/workflows/build.yml` and trigger the workflow.

Artifacts:

- `TNECase-Windows.zip`
- `TNECase-macOS.zip`

## Notes

- Windows and macOS builds both include `gurobipy` packaging hooks.
- The `--add-data` separator is `;` on Windows and `:` on macOS/Linux.
- Shared macOS apps may still need signing and notarization.
