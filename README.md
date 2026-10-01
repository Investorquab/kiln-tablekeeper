# Kiln — Tablekeeper

Kiln is an autonomous software factory built with BAND Desktop. It plans work, coordinates coding-agent seats, implements a service, attacks the result, repairs failures, and independently verifies the output.

**Track:** Tablekeeper  
**Factory:** Kiln  
**Submission:** the stage-by-stage service produced by the factory in the BAND room.

## Repository map

- `FACTORY.md` — how the factory is organized
- `mandates/` — generic mandates for each BAND seat
- `room.json` — full BAND room session, downloaded unchanged after the official run
- `stage-1/` — Tablekeeper Stage 1 service
- `stage-2/` — Stage 1 carried forward and extended
- `stage-3/` — Stage 2 carried forward and extended
- `stage-4/` — Stage 3 carried forward and extended

## Factory flow

```
Plan → Model → Build → Attack → Repair → Retest → Independently Verify
```

The final submission is evidence-backed: the room log shows the collaboration, the Git history shows the produced revisions, and the official harness is used to check each completed stage.

## How to read this repository

Start with `FACTORY.md`, then inspect the seat mandates and `room.json`. Each completed stage contains its own `Dockerfile`, `RUN.md`, and source tree.

## Status

This repository is being populated by the final autonomous BAND run. Only stages actually completed by the band will be submitted.
