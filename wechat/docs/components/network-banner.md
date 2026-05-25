# network-banner

Global "网络不稳定" warning strip. Subscribes to `utils/degradation` and
shows a fixed-position banner at the top of any page that includes it
whenever the local degradation flag is set.

- **Path**: `/components/network-banner/index`
- **Source**: `wechat/components/network-banner/`
- **Backing module**: `wechat/utils/degradation.js`

## Props

None — state is read from `utils/degradation`. The component is reactive:
it `subscribe()`s in `attached` and updates `setData` automatically.

## Events

| Event | `detail` shape | Fires when |
|---|---|---|
| `retry` | `{}` | User taps the banner. Component also calls `degradation.clearDegraded()` synchronously, so subsequent calls start fresh. |

## When does it appear?

Auto-tripped from `services/order.js`:

- `createOrder` — failures tracked under scope `order_submit`
- `payOrder`   — failures tracked under scope `pay`

Threshold: 3 failures within 60 s of type "transport failure" (timeout / DNS)
or HTTP 5xx. 4xx does NOT count. State auto-expires after 5 min.

Can also be tripped manually: `degradation.setDegraded('your_reason')`.

## Example

`pages/patient/home/index.json`:

```json
{
  "usingComponents": {
    "network-banner": "/components/network-banner/index"
  }
}
```

`pages/patient/home/index.wxml`:

```xml
<view class="patient-home">
  <network-banner bind:retry="onNetworkRetry" />
  <!-- rest of the page -->
</view>
```

```js
onNetworkRetry() {
  // optional: re-fetch any data the user was waiting on
  this.refreshHomeData()
},
```

## Gotchas

- The banner is `position: fixed; z-index: 9999`. If your page has a sticky
  header, add `padding-top: 80rpx` to your top container when degraded — or
  swap to a non-fixed style. (We chose fixed because most pages scroll
  freely and we want the warning always visible.)
- Currently wired only on the patient home page. To expose on more pages,
  add `"network-banner": "/components/network-banner/index"` to that page's
  `index.json` and drop `<network-banner />` in the WXML.
- A future refactor could promote this to a global component via `app.json`
  `usingComponents` so every page picks it up automatically.
