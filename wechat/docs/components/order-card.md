# order-card

Order list item used by both patient and companion order lists. Renders
status badge, service label, price, family-member info, and bubbles a
`tap` event with the order id.

- **Path**: `/components/order-card/index`
- **Source**: `wechat/components/order-card/`

## Props

| Name | Type | Default | Required | Notes |
|---|---|---|---|---|
| `order` | `Object` | `{}` | yes | Order record from `services/order.js`. See shape below. |

### `order` shape (minimum)

```ts
{
  id: string,
  status: string,            // key into utils/constants.ORDER_STATUS
  service_type: string,      // key into utils/constants.SERVICE_TYPES
  price: number,             // yuan
  family_member?: {
    name: string,
    relation: string,        // key into utils/familyRelation
  },
  // ...plus whatever the detail page needs
}
```

## Events

| Event | `detail` shape | Fires when |
|---|---|---|
| `tap` | `{ id: string }` | User taps the card. |

## Derived data (internal)

| Field | Derivation |
|---|---|
| `statusInfo` | `ORDER_STATUS[order.status]` → `{ label, color }` |
| `serviceLabel` | `SERVICE_TYPES[order.service_type].label` |
| `priceText` | `formatCurrency(order.price)` (`¥1,234.00`) |
| `familyMemberText` | `"张三（父亲）"` or `''` if no family member |

Updates are observer-driven on the `order` prop, so reassigning the whole
object propagates correctly; mutating nested fields will NOT re-render.

## Example

```json
{ "usingComponents": { "order-card": "/components/order-card/index" } }
```

```xml
<block wx:for="{{orders}}" wx:key="id">
  <order-card order="{{item}}" bind:tap="onOpenOrder" />
</block>
```

```js
onOpenOrder(e) {
  router.navigate('/pages/patient/order-detail/index?id=' + e.detail.id)
},
```

## Gotchas

- Unknown `order.status` falls back to `{ label: '未知', color: '#999' }`.
  Make sure backend enums stay in sync with `utils/constants.ORDER_STATUS`.
- The component is role-agnostic — it does NOT know whether the viewer is a
  patient or companion. Pages that need role-specific CTAs (accept / refund)
  should render those buttons outside the card.
