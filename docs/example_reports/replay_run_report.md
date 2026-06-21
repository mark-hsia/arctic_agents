# Hyphae benchmark report

**Combined score.** 1 / 31 checks passed (3.2 %) across 3 benchmarks.

# Benchmark: junttila2021

**Reference.** Junttila et al. 2021, Microorganisms 9:1347 — Cladonia lichen metagenomes (ENA PRJEB34718)  
**DOI.** [10.3390/microorganisms9071347](https://doi.org/10.3390/microorganisms9071347)

**Score.** 1 / 20 checks passed (5.0 %).

## Stage: mag_qc

| Check | Direction | Paper | Hyphae | Δ | Pass |
|---|---|---:|---:|---:|:---:|
| `busco_ascomycota_complete_L1` | >= | 93.6% | —% | — | FAIL |
| `busco_ascomycota_complete_L2` | >= | 93.2% | —% | — | FAIL |
| `busco_ascomycota_complete_L3` | >= | 93.2% | —% | — | FAIL |
| `busco_ascomycota_complete_L4` | >= | 91.5% | —% | — | FAIL |
| `busco_ascomycota_complete_L34` | >= | 93.2% | —% | — | FAIL |
| `busco_ascomycota_complete_L35` | >= | 93.4% | —% | — | FAIL |

## Stage: bgc_discovery

| Check | Direction | Paper | Hyphae | Δ | Pass |
|---|---|---:|---:|---:|:---:|
| `bgc_count_L1` | >= | 35 | — | — | FAIL |
| `t1pks_count_L1` | >= | 21 | — | — | FAIL |
| `bgc_count_L2` | >= | 28 | — | — | FAIL |
| `t1pks_count_L2` | >= | 12 | — | — | FAIL |
| `bgc_count_L3` | >= | 31 | — | — | FAIL |
| `t1pks_count_L3` | >= | 18 | — | — | FAIL |
| `bgc_count_L4` | >= | 41 | — | — | FAIL |
| `t1pks_count_L4` | >= | 28 | — | — | FAIL |
| `bgc_count_L34` | >= | 33 | — | — | FAIL |
| `t1pks_count_L34` | >= | 20 | — | — | FAIL |
| `bgc_count_L35` | >= | 38 | — | — | FAIL |
| `t1pks_count_L35` | >= | 22 | — | — | FAIL |
| `total_bgcs` | >= | 200 | 0 | -200 | FAIL |

## Stage: assembly

| Check | Direction | Paper | Hyphae | Δ | Pass |
|---|---|---:|---:|---:|:---:|
| `total_samples_assembled` | >= | 6 | 6 | +0 | PASS |


---

# Benchmark: tagirdzhanova2025

**Reference.** Tagirdzhanova et al. 2025 — Reference metagenome of *Cladonia rangiformis* (BMC Biology)  
**DOI.** [10.1186/s12915-025-02428-z](https://doi.org/10.1186/s12915-025-02428-z)

**Score.** 0 / 5 checks passed (0.0 %).

## Stage: bgc_discovery

| Check | Direction | Paper | Hyphae | Δ | Pass |
|---|---|---:|---:|---:|:---:|
| `named_bgc_recovery::grayanic acid` | >= | 1 | — | — | FAIL |
| `named_bgc_recovery::6-hydroxymellein` | >= | 1 | — | — | FAIL |
| `named_bgc_recovery::FR901512` | >= | 1 | — | — | FAIL |
| `named_bgc_recovery::clavaric acid` | >= | 1 | — | — | FAIL |
| `total_bgcs_at_least_paper` | >= | 30 | 0 | -30 | FAIL |


---

# Benchmark: lee2024

**Reference.** Lee et al. 2024, Scientific Reports — Comparative genomics of six Cladonia species (antiSMASH fungal v7.0)  
**DOI.** [10.1038/s41598-024-51895-x](https://doi.org/10.1038/s41598-024-51895-x)

**Score.** 0 / 6 checks passed (0.0 %).

## Stage: bgc_discovery

| Check | Direction | Paper | Hyphae | Δ | Pass |
|---|---|---:|---:|---:|:---:|
| `bgc_count::C. borealis` | >= | 33 | — | — | FAIL |
| `bgc_count::C. grayi` | >= | 27 | — | — | FAIL |
| `bgc_count::C. macilenta` | >= | 31 | — | — | FAIL |
| `bgc_count::C. metacorallifera` | >= | 36 | — | — | FAIL |
| `bgc_count::C. rangiferina` | >= | 35 | — | — | FAIL |
| `bgc_count::C. uncialis` | >= | 28 | — | — | FAIL |


---

