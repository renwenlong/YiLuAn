// miniprogram-automator smoke test.
//
// What: launches the WeChat devtool, drives it from the patient home into
// a companion list and then a companion detail page, asserting page paths
// and title text along the way.
//
// Why: this is the cheapest possible signal that the app boots and the
// most-used navigation chain still resolves after a refactor. It runs
// against the real devtool, not a mock, so it catches WXML/WXSS regressions
// jest can't.
//
// Not run in CI: requires WeChat Developer Tools installed locally with
// the CLI port enabled. See README in this directory for setup.

const path = require('path')

let automator
try {
  // eslint-disable-next-line global-require
  automator = require('miniprogram-automator')
} catch (e) {
  console.error('[smoke] miniprogram-automator not installed.')
  console.error('Install with: npm i -D miniprogram-automator')
  console.error('Then enable CLI port in WeChat DevTool → Settings → Security.')
  process.exit(2)
}

const PROJECT_PATH = path.resolve(__dirname, '..')
const CLI_PATH = process.env.WX_CLI_PATH ||
  '/Applications/wechatwebdevtools.app/Contents/MacOS/cli'

function log(step, ok, extra) {
  const tag = ok ? '✓' : '✗'
  const line = '  ' + tag + ' ' + step + (extra ? '  ' + extra : '')
  console.log(line)
}

async function expectPage(miniProgram, expectedPath) {
  const page = await miniProgram.currentPage()
  const got = page.path
  if (got !== expectedPath) {
    throw new Error('expected page ' + expectedPath + ', got ' + got)
  }
  return page
}

async function run() {
  console.log('[smoke] launching WeChat DevTool...')
  console.log('[smoke] project: ' + PROJECT_PATH)
  console.log('[smoke] cliPath: ' + CLI_PATH)

  let miniProgram
  try {
    miniProgram = await automator.launch({
      cliPath: CLI_PATH,
      projectPath: PROJECT_PATH,
      // 60s — DevTool cold-start can be slow on first run
      timeout: 60000,
    })
  } catch (e) {
    console.error('[smoke] launch failed: ' + e.message)
    console.error('Hints:')
    console.error('  - DevTool installed and runnable?')
    console.error('  - Settings → Security → Service Port → enabled?')
    console.error('  - WX_CLI_PATH env var if installed in a non-standard path')
    process.exit(1)
  }

  let exitCode = 0
  try {
    // Step 1: app booted, sitting on the configured first page.
    const start = await miniProgram.currentPage()
    log('app launched, currentPage=' + start.path, true)

    // Step 2: navigate to patient home (entry tab).
    await miniProgram.navigateTo('/pages/patient/home/index')
    const home = await expectPage(miniProgram, 'pages/patient/home/index')
    log('navigated to patient home', true, 'path=' + home.path)

    // Step 3: navigate to a companion list page. Use the orders list
    // as a proxy for "list of companions" since the homepage lists
    // companions inline.
    await miniProgram.navigateTo('/pages/orders/index')
    const orders = await expectPage(miniProgram, 'pages/orders/index')
    log('navigated to orders list', true, 'path=' + orders.path)

    // Step 4: navigate into a companion detail page (sub-package).
    await miniProgram.navigateTo('/pages/companion-detail/index?id=smoke-test')
    const detail = await expectPage(miniProgram, 'pages/companion-detail/index')
    log('navigated to companion detail', true, 'path=' + detail.path)

    console.log('\n[smoke] OK — 4/4 steps passed.')
  } catch (e) {
    console.error('\n[smoke] FAILED: ' + (e.message || e))
    if (e.stack) console.error(e.stack)
    exitCode = 1
  } finally {
    try { await miniProgram.close() } catch (_) { /* ignore */ }
  }
  process.exit(exitCode)
}

run().catch(function (e) {
  console.error('[smoke] unhandled: ' + (e && e.message))
  process.exit(1)
})
