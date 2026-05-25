# Component Documentation

> Per-component reference for the YiLuAn WeChat mini-program. Each doc page
> covers props, events, slots, and a usage example.
>
> Why not Storybook? WeChat mini-program runtime is incompatible with Storybook
> (no DOM, custom component model). We use plain Markdown so docs live next to
> the code and render natively on GitHub / Notion / any markdown viewer.

## Index

| Component | Doc | Path |
|---|---|---|
| `service-card` | [service-card.md](./service-card.md) | `/components/service-card/index` |
| `companion-card` | [companion-card.md](./companion-card.md) | `/components/companion-card/index` |
| `order-card` | [order-card.md](./order-card.md) | `/components/order-card/index` |
| `network-banner` | [network-banner.md](./network-banner.md) | `/components/network-banner/index` |

## Conventions

All components follow these rules — assume them unless a doc says otherwise.

- **Registration**: declare in the page's `index.json` `usingComponents`, or
  globally in `app.json` for shared chrome (loading-overlay, empty-state,
  tab bars).
- **Events**: use `bind:eventName` on the tag; the handler receives a
  `WechatMiniprogram.CustomEvent` whose `detail` matches the documented shape.
- **Styles**: components own their `.wxss`. Page-level overrides should use
  external classes only when explicitly declared via `externalClasses`.
- **Updates**: when you add/change props or events, update the matching
  `.md` here in the same PR. The `components/README.md` index links here.
