# Vietnam Travel Risk AI — course data foundation

This first milestone contains data snapshots and the small configuration files needed to understand them. It contains no trained model, application code, API, or frontend.

| Path | Contents in this snapshot |
| --- | --- |
| `data/raw/articles_raw.jsonl` | 3,889 collected article records with source and URL metadata. |
| `data/clean/articles_clean.jsonl` | 8,378 article records with extracted text and quality fields. |
| `data/features/articles_features.jsonl` | 8,378 article records with location and rule-based risk features. |
| `data/datasets/stage1_train.csv` | 11,608 text and label rows for training. |
| `data/datasets/stage1_val.csv` | 2,902 text and label rows for validation. |
| `data/external/accidents.csv` | 11 location, date, and title rows. |
| `data/outputs/agg_province_daily.csv` | 1,352 daily province aggregate rows. |
| `configs/provinces.yaml` | Province names, coordinates, codes, and aliases. |
| `configs/keywords.yaml` | Tourism and risk keyword rules. |
| `configs/sources.yaml` | RSS source configuration. |
| `configs/gnews_queries.yaml` | Google News search query configuration. |

Article records contain their own source/URL fields; the configuration files show collection settings. The available files do not establish licenses or complete provenance for every record, including `accidents.csv` and the labeled CSVs. This README makes no claim about third-party reuse rights or a one-to-one lineage between these snapshots.

Model artifacts, model predictions, runtime SQLite state, secrets, and caches are excluded from this milestone.
