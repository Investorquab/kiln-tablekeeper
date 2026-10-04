# Tablekeeper asset map

This folder is designed to be copied into `stage-4/assets/` and then integrated by the Band Implementer.

## Runtime images

| File | Intended placement | Notes |
|---|---|---|
| `images/hero-restaurant.webp` | `/welcome` landing-page hero | Use as the hero visual with a dark/green overlay if text sits above it. |
| `images/restaurant-ember-oak.webp` | Venue card | Demo venue: **Ember & Oak** — grill / steakhouse. |
| `images/restaurant-green-fork.webp` | Venue card | Demo venue: **The Green Fork** — Italian / pizza. |
| `images/restaurant-palm-plate.webp` | Venue card | Demo venue: **Palm & Plate** — African / local / seafood. |
| `images/restaurant-olive-room.webp` | Venue card | Demo venue: **The Olive Room** — Mediterranean / waterfront. |
| `images/restaurant-detail.webp` | Restaurant detail / secondary hero | Generic venue interior/detail. |
| `images/food-dish.webp` | Discovery/detail accent | Food close-up; use sparingly. |
| `images/table-setting.webp` | Booking-side visual / decorative card | General table-setting image. |

## SVG illustrations

- `illustrations/reservation-confirmed.svg` — confirmation state / receipt-success panel.
- `illustrations/leaf-decoration.svg` — decorative corner or section divider.
- `illustrations/table-setting.svg` — booking/discovery decoration.
- `illustrations/wine-glass.svg` — culinary motif; optional.
- `illustrations/cutlery.svg` — culinary motif; optional.
- `illustrations/restaurant-line-art.svg` — landing-page decorative line art.
- `illustrations/background-shape.svg` — soft background ornament.

## SVG icons

Use the icons as local `<img>`/`<svg>` assets or inline them when convenient: `calendar`, `guests`, `location`, `clock`, `table`, `availability`, `shield`, `retry`, `search`.

## Branding

- `brand/tablekeeper-logo.svg` — wordmark for landing/auth areas.
- `brand/favicon.svg` — favicon / browser icon.

## Demo data alignment

The current Stage 4 source does not ship populated normal-startup restaurant data. The integration should seed four attractive demo venues using the exact names above and associate the matching image file with each venue. Keep the existing test-fixture behavior intact so official tests remain deterministic.

## Offline requirement

Do not load images from remote URLs. The isolated judging environment must be able to build and run with the repository alone.
