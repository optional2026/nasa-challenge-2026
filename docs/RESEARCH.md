# Research integrated into ASTRA

All sources are recorded in `backend/astra/knowledge/data/sources.json` with a verification status. Online sources
were checked on 2026-11-14 by the build agent; status `VERIFIED_ONLINE` means the document was found at the URL and
the cited point was confirmed in its text or search extract.

## Verified NASA facts used in the software

| Fact | Where used | Source |
|---|---|---|
| The five hazards: space radiation, isolation and confinement, distance from Earth, gravity fields, hostile/closed environments; hazards are interconnected | Hazard model, library | NASA HRP hazards page; NTRS 20230015521 |
| HRP / HSRB risk list (bone fracture, renal stone, SANS, sensorimotor, sleep loss/circadian/work overload, altered immune response, host-microorganism, behavioral, cardiovascular adaptations, toxic exposure, radiation carcinogenesis) | 12 risk definitions | nasa.gov/hrp/risks; nasa.gov/human-system-risks; NTRS 20230017691 |
| Hazard→risk links: distance → autonomous medical care; isolation → behavioral, sleep, team; hostile/closed → CO₂, toxic exposure, water, food, immune | Risk–hazard relationships | NTRS 20190001026 |
| NASA-STD-3001 Vol 1 Rev C [V1 6001] rationale recommends an **8.5-hour sleep period** in crew schedule planning | Scheduling-reference rule (applied to the *scheduled* sleep opportunity only, informational) | NASA-STD-3001 Vol 1 Rev C |
| [V1 6002] private medical communication; stored/forward when delays exist; [V1 3004] in-mission medical care | Private communication design, store-and-forward sync | NASA-STD-3001 Vol 1 Rev C; OCHMO-TB-016 |
| [V1 4029] ALARA; [V1 4030] career space permissible exposure limit | Radiation risk description (no limit is applied as an alert) | NASA-STD-3001 Vol 1 Rev C |
| NASA-STD-3001 Vol 2 Rev D **[V2 6004] average 1-hour ppCO₂ in the habitable volume ≤ 3 mmHg** | CO₂ environmental rule (environment alert, not a medical diagnosis) | OCHMO-TB-004 |
| Crew symptoms attributed to CO₂ from 2.3 mmHg; wide inter-individual variability | CO₂ limitation text | NTRS 20150019624 |
| Radiation countermeasures: shielding, monitoring, event determination, dosimetry, timely reporting; area and personal monitoring [V2 6161]/[V2 6162] | Radiation module, dosimeter adapters | OCHMO-TB-020; HRP space radiation page; PMC10919966 |
| Average in-flight sleep ≈ 6 h; sleep quality/quantity factors | Sleep risk description | OCHMO-TB-041 |
| All astronauts exercise to counteract losses in bone density, muscle strength and cardiovascular performance | Exercise countermeasure; "adherence is not bone density" limitation | nasa.gov/hrp/risks |

## Things ASTRA deliberately does not claim

* No clinical thresholds for heart rate, blood pressure, SpO₂, temperature, glucose or sleep are asserted. Deviation
  rules are relative to the astronaut's own approved baseline and are labelled DEMONSTRATION_ONLY.
* No diagnosis of SANS, immune dysfunction, kidney stones, cardiovascular disease, nutrient deficiency or psychiatric
  conditions. Each risk lists what ASTRA cannot determine.
* No treatment or medication instructions. Procedures are synthetic workflow placeholders that point to the
  mission-approved checklist; medication records require an approved-instruction reference and a medical role.
* No hardware compatibility claims. All devices are simulated (`hardware_validated = false`).
* Temporal overlays (e.g. heart rate with CO₂) carry an explicit "no causation" disclaimer.

## Sources not independently retrieved

* The individual 2026 Space Apps challenge page (`SRC-CHALLENGE-2026`) — requirements were taken from the challenge
  text supplied by the team. Status: `PROVIDED_BY_TEAM`.
* OCHMO technical-brief index page (`REFERENCED_IN_VERIFIED_SOURCE`).
