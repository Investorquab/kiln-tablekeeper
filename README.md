# Kiln — Tablekeeper

<p align="center">
  <strong>An autonomous software factory that plans, builds, attacks, repairs, and verifies software.</strong>
</p>

<p align="center">
  <a href="https://kiln-tablekeeper.vercel.app/">Live Demo</a> ·
  <a href="https://github.com/Investorquab/kiln-tablekeeper">Repository</a> ·
  <a href="https://github.com/Investorquab/kiln">Kiln Factory</a>
</p>

> **WeAreDevelopers × BAND Dark Factory Hackathon**
>
> Tablekeeper is the product Kiln used to demonstrate an autonomous, evidence-driven software factory: multiple specialized agent seats collaborate through BAND to plan work, write acceptance tests, implement the service, investigate failures, review the result, and integrate a verified build.

## 🎥 Demo

**Live application:** https://kiln-tablekeeper.vercel.app/

[![Tablekeeper Demo](https://img.youtube.com/vi/uPZeSH1m5MY/maxresdefault.jpg)](https://youtu.be/uPZeSH1m5MY)

**Watch the full demo on YouTube:** https://youtu.be/uPZeSH1m5MY

> The demo shows both sides of the project: the finished Tablekeeper product and the Kiln/BAND factory that produced and verified it.

---

## Contents

- [What is Kiln?](#what-is-kiln)
- [What is Tablekeeper?](#what-is-tablekeeper)
- [Why this matters](#why-this-matters)
- [How the factory works](#how-the-factory-works)
- [Factory seats](#factory-seats)
- [Product flow](#product-flow)
- [Validation](#validation)
- [Repository structure](#repository-structure)
- [Running Tablekeeper](#running-tablekeeper)
- [Deployment](#deployment)
- [Evidence](#evidence)
- [Roadmap](#roadmap)
- [License](#license)

---

## What is Kiln?

**Kiln is a software factory, not just a coding agent.**

The factory turns a product mandate into working software through a controlled sequence of specialized roles:

**Plan → Test → Build → Attack → Repair → Review → Integrate → Verify**

Each seat has a bounded responsibility and produces evidence that can be traced through the BAND room, repository history, acceptance work, and validation runs.

The goal is simple:

> **Software that can show how it was built, what was tested, what failed, what was repaired, and why the final result can be trusted.**

---

## What is Tablekeeper?

Tablekeeper is an OpenTable-style restaurant reservation experience built around a real HTTP service.

A diner can:

1. Discover a restaurant.
2. Choose a date and party size.
3. Inspect available seating.
4. Select a table.
5. Reserve the table.
6. Receive a stable confirmation reference.
7. Look up and manage the reservation.

### Seeded restaurants

| Restaurant | Style |
|---|---|
| **Ember & Oak** | Grill / Steakhouse |
| **The Green Fork** | Italian / Pizza |
| **Palm & Plate** | African / Local / Seafood |
| **The Olive Room** | Mediterranean / Seafood / Modern |

---

## Why this matters

Most AI coding workflows focus on **generating code**.

Kiln focuses on the larger engineering loop:

- What should be built?
- How do we prove the requirement works?
- What happens when the implementation fails?
- Can another agent independently attack the result?
- Can failures be investigated and repaired?
- Can the final build be validated outside the implementation loop?

BAND provides the collaborative agent-room infrastructure. Kiln provides the factory process and evidence model around it.

---

## How the factory works

The Tablekeeper factory is divided into specialized seats:

```text
                    PRODUCT MANDATE
                          │
                          ▼
                     ┌─────────┐
                     │ PLANNER │
                     └────┬────┘
                          │
                          ▼
                  ┌──────────────┐
                  │ TEST AUTHOR  │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ IMPLEMENTER  │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ INVESTIGATOR │
                  └──────┬───────┘
                         │
                         ▼
                    ┌──────────┐
                    │ REVIEWER │
                    └────┬─────┘
                         │
                         ▼
                   ┌───────────┐
                   │ INTEGRATOR│
                   └─────┬─────┘
                         │
                         ▼
                    VERIFIED BUILD
```

The important distinction is that the same agent is not responsible for deciding that its own work is correct.

---

## Factory seats

| Seat | Responsibility |
|---|---|
| **Planner** | Turns the mandate into an actionable implementation plan. |
| **Test Author** | Defines acceptance coverage and executable checks. |
| **Implementer** | Builds the requested functionality. |
| **Investigator** | Attacks failures, diagnoses root causes, and proposes repairs. |
| **Reviewer** | Independently examines the implementation and evidence. |
| **Integrator** | Coordinates the final integration and shipped state. |

This separation creates an evidence trail rather than a single opaque "AI wrote the app" step.

---

## Product flow

For a presentation, the fastest end-to-end flow is:

```text
/welcome
   ↓
Find a table
   ↓
Choose restaurant
   ↓
Choose date + party size
   ↓
Inspect availability
   ↓
Select table
   ↓
Reserve
   ↓
Show confirmation reference
   ↓
Open Your Booking
   ↓
Look up reservation
```

The `/welcome` page provides the public introduction, while the reservation application remains available at `/`.

---

## Validation

The current shipped milestone is **Stage 4**.

The Stage 4 baseline was cloned into a fresh environment on the VPS and checked using the official Tablekeeper harness in isolated Docker mode.

### Shipped checks

| Stage | Result |
|---|---|
| Stage 1 | ✅ Pass |
| Stage 2 | ✅ Pass |
| Stage 3 | ✅ Pass |
| Stage 4 | ✅ Pass |

**Highest contiguous stage:** 4  
**Claimed shipped stage:** 4

The Stage 4 Docker image also starts as a standalone HTTP service and responds successfully to:

```http
GET /health

{"status":"ok"}
```

A green shipped-check run is evidence of readiness, not a guarantee against every hidden judge case.

---

## Repository structure

```text
.
├── FACTORY.md
├── mandates/
├── room.json
├── stage-1/
├── stage-2/
├── stage-3/
├── stage-4/
├── Dockerfile.vercel
├── LICENSE
└── README.md
```

### Important files

- **FACTORY.md** — factory architecture and seat responsibilities.
- **mandates/** — generic mandates supplied to the BAND seats.
- **room.json** — BAND room export used as collaboration evidence.
- **stage-1/** — first Tablekeeper service milestone.
- **stage-2/** — Stage 1 carried forward and extended.
- **stage-3/** — Stage 2 carried forward and extended.
- **stage-4/** — current shipped Stage 4 service.
- **Dockerfile.vercel** — public presentation deployment definition.

Each completed stage contains its own Dockerfile, RUN.md, and service source.

---

## Running Tablekeeper

The official hackathon deliverable is the containerized stage service.

Judges can build the stage Dockerfile and communicate with the service over HTTP.

For example:

```bash
docker build -t tablekeeper ./stage-4
docker run --rm -p 8000:8000 tablekeeper
```

Then verify the service:

```bash
curl http://localhost:8000/health
```

> Check the stage-specific `RUN.md` for the authoritative commands and environment required by that stage.

---

## Deployment

The repository also contains `Dockerfile.vercel` for the public Vercel presentation deployment.

**Live demo:** https://kiln-tablekeeper.vercel.app/

The Vercel deployment is presentation infrastructure. It is separate from the official isolated Docker validation used for the hackathon deliverable.

Because the current service keeps application state in memory, the public demo should be treated as an ephemeral demonstration rather than a persistent production reservation system.

---

## Evidence

The factory's evidence is distributed across several artifacts:

- BAND room export
- Agent mandates
- Stage acceptance work
- Repository commits
- Review and investigation output
- Docker validation
- Final shipped stage

The intent is that the factory can demonstrate not only **what it built**, but **how it reached the result and how the result was checked**.

Start with **[FACTORY.md](FACTORY.md)** to understand the factory itself.

---

## Roadmap

The official challenge stages stop at Stage 4.

### Stage 5 — Product Polish

Planned improvements include:

- premium restaurant-oriented Welcome experience
- improved restaurant discovery
- tighter Find-a-table layout
- clearer availability presentation
- improved combined-table treatment
- polished reservation-success modal
- redesigned confirmation card
- shareable reservation invitation codes
- shared reservation joining
- owner-only mutation permissions
- stronger authentication flow
- My Reservations / Join Reservation experience
- improved authenticated navigation
- restaurant-focused login/signup
- tasteful motion and micro-interactions
- stronger 375px/mobile composition
- accessibility and reduced-motion improvements

### Stage 6 — Adversarial Audit Suite

Kiln will deliberately attack the finished product through black-box HTTP checks, including:

- concurrent booking bursts
- idempotency retry storms
- cancel/rebook races
- PATCH/create contention
- timezone and daylight-saving edge cases
- combined-table collisions
- closure/replan consistency
- recovery and error behaviour

The goal is to document failures deliberately induced by the factory and the evidence that the system resisted or recovered from them.

---

## Visual direction

Tablekeeper uses a warm cream, deep green, and warm-gold visual language with editorial typography and restaurant-oriented imagery.

**Warm · Premium · Editorial · Modern · Trustworthy · Lively**

The goal is for Tablekeeper to feel like a real hospitality product rather than a generic CRUD application.

---

## License

This project is licensed under the **MIT License**.

See [LICENSE](LICENSE) for the full license text.

Built for the **WeAreDevelopers × BAND Dark Factory Hackathon**.
