# companion-card

Companion (陪诊师) summary card. Used on patient home, search results, and
companion lists. Shows avatar, name, rating, distance, and optionally a
"book" CTA.

- **Path**: `/components/companion-card/index`
- **Source**: `wechat/components/companion-card/`

## Props

| Name | Type | Default | Required | Notes |
|---|---|---|---|---|
| `companion` | `Object` | `{}` | yes | Companion record. Expects at least `id`, `name`, `avatar`, `rating`, `distance` (km, number). |
| `showBook` | `Boolean` | `false` | no | When true, renders the "立即预约" CTA and emits `bind:book` on tap. |

### `companion` shape

```ts
{
  id: string,
  name: string,
  avatar?: string,        // URL
  rating?: number,        // 0–5, one decimal
  review_count?: number,
  distance?: number,      // km, one decimal
  tags?: string[],        // e.g. ["三甲熟路", "陪老人"]
}
```

## Events

| Event | `detail` shape | Fires when |
|---|---|---|
| `tap` | `{ id: string }` | User taps the card body (navigate to detail). |
| `book` | `{ id: string }` | User taps the CTA (requires `showBook=true`). |

## Example

```json
{ "usingComponents": { "companion-card": "/components/companion-card/index" } }
```

```xml
<block wx:for="{{companions}}" wx:key="id">
  <companion-card
    companion="{{item}}"
    showBook="{{true}}"
    bind:tap="onOpenCompanion"
    bind:book="onBookCompanion"
  />
</block>
```

```js
onOpenCompanion(e) {
  router.navigate('/pages/companion-detail/index?id=' + e.detail.id)
},
onBookCompanion(e) {
  router.navigate('/pages/patient/create-order/index?companionId=' + e.detail.id)
},
```

## Gotchas

- `distance` is rendered as-is; pre-round on the server or in the page to
  one decimal place.
- Avatar fallback is handled inside the component — pass an empty string,
  not `null`, to avoid `[object Object]` artifacts in WXML.
