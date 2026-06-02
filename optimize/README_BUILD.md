# TNE Case Packaging Kit

These files now delegate to the repo-root build flow.

## Windows build

Run either command:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

or from repo root:

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
