# Green computing: before vs after (S3-05)

Same script (`scripts/measure_green.py`), same laptop (Intel Core i7-1165G7 (this laptop), 11.8 GB RAM), measured 2026-10-27.
**Before** = the CIA-3 submission (commit `cf9d87e`, 11 Oct 2026). **After** = commit `99b3f7f`.
Each server figure is the median of 30 requests after a warm-up; page figures are the median of 5 fresh loads in headless Chrome with the cache off.

| Measure | Before | After | Change |
|---|---|---|---|
| Model file | 27.88 MB | 4.63 MB | -83% |
| Server memory, model loaded | 230.4 MB | 209.6 MB | -9% |
| Server memory, after 90 requests | 250.7 MB | 233.6 MB | -7% |
| Signed passport with model prediction: time | 215.7 ms | 76.6 ms | -64% |
| Signed passport with model prediction: CPU | 221.4 ms | 72.9 ms | -67% |
| Assessment: time | 4.9 ms | 4.9 ms | same |
| Research data: time | 45.3 ms | 46.8 ms | +3% |
| First-page JavaScript (gzip) | 73.8 kB | 75.0 kB | +2% |
| First-page CSS (gzip) | 31.6 kB | 32.9 kB | +4% |
| Home page transferred | 180.4 kB | 180.4 kB | same |
| Home page load time (local) | 649 ms | 650 ms | same |
| Whole build on disk (incl. on-demand parts) | 895.2 kB | 2991.0 kB | +234% |
| Estimated energy per 1,000 passports | 0.43 Wh | 0.142 Wh | -67% |
| Estimated carbon per 1,000 passports | 0.288 g CO2e | 0.095 g CO2e | -67% |

## Reading it

- **The model** went from 300 trees to 150, saved compressed: a much smaller file and about a third of the CPU per prediction, with the same end-of-life recall and calibration (`app_data/model_size_experiment.json`).
- **The first page stayed the same size** although about fifteen features were added, because new pages, the sign-in window, the results page and the PDF reader load only when used.
- **The whole build is bigger on disk** mainly because of the PDF reader added for verifying PDF passports (about 1.4 MB). It is downloaded only by someone who uploads a PDF, so it costs nothing for everyone else.
- **The assessment response grew** (more cards: usage fit, repair outlook, rights, carbon range) for the same time and CPU.

**Energy method (an estimate, not a meter reading):** server CPU seconds x 7.0 W per busy core (TDP 28 W / 4 cores); carbon at 670 gCO2e/kWh. An estimate from measured CPU time, not a meter reading. Absolute values are tiny because each request is short; the useful number is the relative change.
