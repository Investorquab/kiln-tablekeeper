# Kiln Factory

## Purpose

Kiln is a generic software factory. A job enters as a specification; the band decomposes it, models the important invariants, implements the work, independently attacks the result, repairs verified failures, retests, and performs an independent verification before a stage is accepted.

The factory is domain-agnostic. The current workload is the Tablekeeper track.

## Seats

The final BAND room uses six seats:

- Planner — decomposes the job and coordinates the build sequence.
- Test author — turns requirements and invariants into executable acceptance checks.
- Implementer — implements the stage and records the committed revision.
- Investigator — independently attacks the implementation and reports failures.
- Reviewer — diagnoses verified failures, makes repairs, and adds regression coverage.
- Integrator — independently verifies the final revision and acceptance evidence.

Each seat has a generic mandate in `mandates/`.

## Handoff discipline

Every delegated task must contain the complete task/specification needed by the receiving seat and the absolute result-repository path. Seats address one another by their literal BAND `@handle` values. The implementer reports the full committed revision. Review and verification must check the handed-off revision rather than relying on a human claim that work is complete.

## Acceptance discipline

A stage is accepted only after:
1. implementation exists in the correct stage folder;
2. the service builds and starts from its own Dockerfile and RUN.md;
3. adversarial checks have been run independently;
4. verified failures are repaired where necessary;
5. the final revision is independently verified;
6. the official harness is run against the stage.

A green local test is not sufficient evidence by itself.

## Evidence

The final evidence set is:
- full BAND room session in `room.json`;
- Git history for the stage revisions;
- `Dockerfile` and `RUN.md` for every submitted stage;
- official harness reports kept outside the result repository while iterating;
- documentation of design choices, failure/recovery and measured time/model usage when available.

## Design principles

The factory separates planning, implementation, attack, repair and independent verification so one seat is not the sole judge of its own work. It also treats handoffs and committed revisions as first-class evidence.

## Submission boundary

This repository is the final result repository for the chosen Tablekeeper track. Development/rehearsal material from the earlier Kiln factory repository is not represented as official BAND-generated evidence.

Before submission, re-read `room.json`, remove/replace any credential-like value as required by the official guide, clone the repository fresh, run the offline harness check, then run the stage harnesses in the fresh clone.
