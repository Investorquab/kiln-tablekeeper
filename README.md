# Kiln — Tablekeeper

Kiln is an autonomous software factory built with BAND Desktop. It plans work, coordinates coding-agent seats, implements a service, attacks the result, repairs failures, and independently verifies the output.

**Track:** Tablekeeper  
**Factory:** Kiln  
**Current shipped milestone:** Stage 4  
**Core application baseline:** 2ad5f84a533ecf94c25735cc04b034bf2d00d326

## What Tablekeeper is

Tablekeeper is a restaurant reservation experience built around a real HTTP service.

A diner can:

1. Discover a restaurant.
2. Choose a date and party size.
3. Inspect available seating.
4. Reserve a table.
5. Receive a stable confirmation reference.
6. Look up and manage a reservation.

The product includes four seeded demo restaurants on normal startup:

- **Ember & Oak** — grill / steakhouse
- **The Green Fork** — Italian / pizza
- **Palm & Plate** — African / local / seafood
- **The Olive Room** — Mediterranean / seafood / modern

## Demo flow

For a presentation, use this sequence:

/welcome  
→ choose Find a table  
→ select a restaurant  
→ choose date + party size  
→ inspect live availability  
→ select a table  
→ reserve  
→ show the confirmation reference  
→ open Your booking  
→ look up the reservation using the reference.

The /welcome page is the public introduction. The real reservation application remains at /.

## Repository map

- FACTORY.md — how Kiln is organized and how work is divided between seats
- mandates/ — generic mandates for the BAND seats
- room.json — full BAND room export used to evidence the collaboration
- stage-1/ — Tablekeeper Stage 1 service
- stage-2/ — Stage 1 carried forward and extended
- stage-3/ — Stage 2 carried forward and extended
- stage-4/ — Stage 3 carried forward and extended

Each completed stage contains its own Dockerfile, RUN.md, and service source.

## Factory flow

Plan → Test → Build → Attack → Repair → Retest → Independently Verify

Kiln separates planning, acceptance work, implementation, investigation, review, and integration so the resulting code can be traced back to the room and the commits that produced it.

## Validation

The current Stage 4 baseline was cloned into a fresh environment on the VPS and checked with the official Tablekeeper harness in isolated Docker mode.

The final available shipped-check run reported:

stage-1: pass
stage-2: pass
stage-3: pass
stage-4: pass

highest contiguous stage: 4
claimed stage: 4 on the shipped checks

The Stage 4 Docker image also starts as a standalone HTTP service and responds successfully to:

GET /health
→ {"status":"ok"}

The official harness contains additional tests that are not shipped to teams. A green shipped-check run is therefore evidence of readiness, not a guarantee against every hidden judge case.

## Runtime and deployment

The official hackathon deliverable is the containerized stage service. Judges build the stage Dockerfiles themselves and communicate with the service over HTTP.

For a public presentation/demo, this repository also includes a Vercel container deployment definition in Dockerfile.vercel. Vercel supports OCI-compatible container images as Vercel Functions and automatically detects a root Dockerfile.vercel for this deployment path.

The Vercel demo is presentation infrastructure, not a replacement for the hackathon's isolated Docker validation.

Because the current service keeps its application state in memory, the public demo should be treated as an ephemeral demonstration rather than a persistent production booking system.

## Local assets

Stage 4 bundles its restaurant photography, icons, illustrations, logo, and favicon in stage-4/assets/.

The browser serves these files locally, so the experience does not depend on a CDN or third-party runtime image host.

The visual assets were created specifically for Tablekeeper by the team using AI image generation and custom SVG artwork. Asset provenance and placement notes live under stage-4/assets/docs/.

## Roadmap — next internal factory phases

The official challenge stages stop at Stage 4. The following are planned product iterations, not additional official challenge stages.

### Stage 5 — Product Polish

The next product iteration will focus on the parts identified during our manual UI audit:

- make the Welcome experience more premium and restaurant-oriented
- improve restaurant cards and discovery
- tighten the Find-a-table layout and reduce excessive scrolling
- make availability easier to scan
- give combined-table options clearer visual treatment
- show reservation success immediately in a polished modal/dialog instead of requiring a long scroll
- redesign the confirmation card and make the reference more prominent
- make confirmation/reference codes shareable invitation codes
- allow authenticated friends to join an existing reservation without changing its party size or seating
- preserve owner-only mutation permissions
- preserve the reference through sign-in/signup before reservation details are revealed
- redesign Your Booking around My Reservations and Join a Shared Reservation
- improve authenticated navigation so public Welcome navigation does not remain awkwardly prominent
- give login/signup a stronger restaurant identity
- add tasteful motion and micro-interactions
- improve 375px/mobile composition
- strengthen accessibility and reduced-motion behavior

### Stage 6 — Adversarial Audit Suite

After Stage 5, Kiln will deliberately attack the finished product through black-box HTTP checks.

Planned scenarios include:

- concurrent booking bursts against the same table/time
- idempotency retry storms
- cancel/rebook races
- PATCH/create contention
- timezone and daylight-saving edge cases
- combined-table collisions
- closure/replan consistency
- recovery and error behavior

The purpose of this suite is to document the failures we deliberately tried to induce and the evidence that the system resisted them.

## Visual design direction

Tablekeeper uses a warm cream, deep green, and warm-gold palette with editorial typography and restaurant-oriented imagery.

The intended direction is:

**Warm · Premium · Editorial · Modern · Trustworthy · Lively**

The product should feel like a real hospitality experience rather than a generic CRUD application.

## Factory evidence

The full room export, mandates, repository history, acceptance work, review messages, and independent validation together form the evidence trail for the factory.

Read FACTORY.md first, then the mandates, room export, and stage folders.

## License

This project was created for the WeAreDevelopers × BAND Dark Factory hackathon.
