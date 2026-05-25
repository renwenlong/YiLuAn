# wechat/e2e — Local smoke tests

`miniprogram-automator` driven end-to-end smoke against the real WeChat
Developer Tools. **Not run in CI** — it needs the GUI devtool installed.

## What it covers

`smoke.js` walks:

1. App launch
2. → `pages/patient/home/index` (patient home)
3. → `pages/orders/index`       (orders list / companion list proxy)
4. → `pages/companion-detail/index?id=…` (detail page)

If any step fails, the script exits non-zero with a diagnostic line.

## One-time setup

1. Install WeChat Developer Tools (Stable channel) from
   <https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html>.
2. Open Settings → Security → enable "服务端口 / Service Port".
3. Install the automator dep (devDependency, kept out of `package.json` by
   default so CI doesn't pull a 100 MB package nobody runs):

   ```bash
   cd wechat
   npm install --no-save miniprogram-automator
   ```

## Running

```bash
cd wechat
node e2e/smoke.js
```

On macOS the script defaults to `/Applications/wechatwebdevtools.app/Contents/MacOS/cli`.
Override on Windows / non-standard installs:

```bash
WX_CLI_PATH="C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" \
  node e2e/smoke.js
```

Expected output:

```
[smoke] launching WeChat DevTool...
  ✓ app launched, currentPage=pages/patient/home/index
  ✓ navigated to patient home  path=pages/patient/home/index
  ✓ navigated to orders list   path=pages/orders/index
  ✓ navigated to companion detail  path=pages/companion-detail/index

[smoke] OK — 4/4 steps passed.
```

## Why no CI integration?

`miniprogram-automator` needs the DevTool GUI process running, which means
either an X server in CI (heavy) or a macOS runner with the devtool image
preinstalled. Until we accept that cost, smoke runs as a local pre-release
check. Track in: **TODO** — promote to a nightly job once a self-hosted
macOS runner is provisioned.
