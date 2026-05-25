# service-card

Patient-home "3-tier service" presentation card. Renders one of the predefined
service types (basic / standard / premium) with title, description, price,
and an active/selected highlight.

- **Path**: `/components/service-card/index`
- **Source**: `wechat/components/service-card/`

## Props

| Name | Type | Default | Required | Notes |
|---|---|---|---|---|
| `type` | `String` | `''` | yes | Key into `utils/constants.SERVICE_TYPES` (e.g. `'basic'`, `'standard'`, `'premium'`). Drives all displayed content. |
| `active` | `Boolean` | `false` | no | Visual highlight when this card is the selected service. |

## Events

None. Wrap the tag and bind `tap` on the parent if you need selection:

```xml
<view bindtap="onPickService" data-type="standard">
  <service-card type="standard" active="{{picked === 'standard'}}" />
</view>
```

## Data (internal)

Component derives `info` (from `SERVICE_TYPES[type]`) and a pre-formatted
`priceText` (`¥1,200.00`) via an observer on `type`. Parent should not write
to internal data.

## Example

`pages/patient/home/index.json`:

```json
{
  "usingComponents": {
    "service-card": "/components/service-card/index"
  }
}
```

`pages/patient/home/index.wxml`:

```xml
<view class="service-row">
  <service-card type="basic"    active="{{picked === 'basic'}}" />
  <service-card type="standard" active="{{picked === 'standard'}}" />
  <service-card type="premium"  active="{{picked === 'premium'}}" />
</view>
```

## Gotchas

- `type` must match a key in `SERVICE_TYPES`. Unknown values render empty —
  validate upstream.
- Price is formatted from `info.price` (number, in yuan) via `formatCurrency`.
  Don't pre-format and pass a string.
