# Player-specific non-QB injury replacement-gap features: chronological test

Experimental performance/participation proxies, **not calibrated individual player point values**.
The peer benchmark is not a confirmed active replacement.
Valued report absences: 7992; unvalued report absences: 2533.

| Candidate | 2025 ATS | 2025 ATS >=3.5 | 2025 margin MAE | 2026 W1–8 ATS | 2026 ATS >=3.5 | 2026 margin MAE |
|---|---:|---:|---:|---:|---:|---:|
| baseline_unscaled | 146–138–1 | 62–65–0 | 10.40 | 60–55–6 | 23–19–2 | 9.68 |
| nonqb_counts_unscaled | 135–149–1 | 68–68–0 | 10.55 | 62–53–6 | 23–17–2 | 9.63 |
| nonqb_counts_std | 144–140–1 | 61–59–0 | 10.35 | 58–57–6 | 25–21–0 | 9.78 |
| player_signed_gap_std | 142–142–1 | 59–56–0 | 10.31 | 61–54–6 | 24–21–0 | 9.80 |
| player_positive_gap_std | 143–141–1 | 60–58–0 | 10.32 | 61–54–6 | 24–21–0 | 9.81 |
| counts_plus_positive_gap_std | 143–141–1 | 61–59–0 | 10.34 | 59–56–6 | 25–22–0 | 9.82 |

## Promotion gate

No change to the public model unless improvements replicate across years and real future frozen games.
Next requirement: verify active next-man-up depth and estimate performance *above actual replacement*.
