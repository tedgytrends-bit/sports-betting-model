# Week 11 Sunday morning refresh

The user supplied 12 Bovada Sunday/Monday quotes at approximately 8:24 a.m. Central on November 22. The new immutable snapshot is nfl_week11_bovada_sunday_2026-11-22T1424Z.csv. Original Thursday IND–HOU scores, quote and grades remain field-for-field unchanged.

The existing Baseline and Injury pipelines were rerun using current public nflverse play-by-play, the schedule including Thursday's completed game, the latest saved final injury report snapshot, the current Week 11 active roster and checked QB inputs. All 24 projected starters passed the roster gate. Existing model parameters, the five-point per-team QB cap and margin-only allocation remain in force.

Arizona confirmed Josh Johnson starts after downgrading Carson Beck to OUT on November 21. The manual content attestation passed the existing source and timestamp validator. Johnson has 163 prior model-counted dropbacks and a limited-sample label. His QB shift reaches the existing five-point cap. The resulting near-even projected margin is uncertain and is shown with a limited-history warning. It is a model forecast and has no validated profitable betting interpretation.

Baker Mayfield remains officially QUESTIONABLE. The Sunday NFL Network report says he will start, and he remains the expected QB in the Sunday model. Geno Smith has no final injury designation after full Friday participation. Remaining scheduled starters are provisional, with Arizona's independently confirmed starter clearly distinguished in the source audit. Official game-day inactives were pending at the time of this morning release. Miami's Kyle McCord has 36 prior model-counted dropbacks and remains insufficient-data.

Sources checked:
- https://www.azcardinals.com/news/josh-johnson-start-confirmed-after-carson-beck-downgraded
- https://www.nfl.com/news/buccaneers-baker-mayfield-will-play-vs-lions
- https://www.newyorkjets.com/news/jets-injury-report-week-11-vs-chargers-friday-11-20-2026
- https://amp.nfl.com/news/nfl-week-11-injury-report-2026-season
- https://www.nbc.com/nbc-insider/nfl-starting-quarterbacks-full-list

The public board reads the new Sunday model snapshot, displays final injury designations, updated market spreads/totals and QB evidence, and keeps TNF first with its final score and grades. Pending Results picks use the same updated quotes and projections. All previous 88 final model-game rows remain identical. The original Sunday source versions and initial Thursday forecasts remain separately timestamped.

Local validation passed 156 tests plus the Results DOM tests, score/total arithmetic, whole-slate roster checks, manual Johnson attestation, and preservation of TNF and earlier finals. No paid NFLMeta or EndzoneAPI requests were made. New forecast and QB audits are saved under data/public_snapshots/nfl_week11_*2026-11-22* with an input-hash manifest.

Deployment recovery uses a unique Pages artifact name per workflow run and attempt and checks artifact discovery before deploying. The deploy action’s separate artifact-service listing returned zero artifacts even after the REST API confirmed the uploaded artifact. The workflow now deploys the REST-discovered artifact ID directly through GitHub’s Pages API using the existing OIDC identity and waits for successful completion. Unique names also avoid duplicate artifacts on retries. The change is limited to deployment reliability.
