# Independent public dataset and reciprocal-binding review

Decision: **ACCEPT_PUBLIC_DATASET_AND_RECIPROCAL_BINDINGS**. Verification completed 2026-11-02T04:44:15.538295+00:00.

I independently made anonymous GET-only requests to dataset [record 23875194](https://zenodo.org/records/23875194), versions/latest and the complete files subresource, then streamed both full files with cache-busting URLs. No publisher verification function was imported and no Authorization header was supplied. All checks exited 0. No files were uploaded, deleted or changed by the reviewer.

The public record and latest both identify dataset 23875194, published and publicly accessible, DOI `10.5281/zenodo.23875194`, concept `10.5281/zenodo.23875193`. Title, description, version 1.0.0, publication date, publisher, English language, CC BY 4.0, sole creator/ORCID, subjects and reciprocal relation exactly match the independently accepted dataset metadata. Its canonical metadata digest remains `44cdcc69a3c55fcab06c8021c6e0bd25580c47ec60dd97b2c3a9973d94c915d6`. The description preserves the registered negative result and distinguishes evidence integrity from application qualification.

The embedded record and separate complete files inventory contain exactly two files, without extras:

- `softqp-coupled-study-v1.zip`: 429502979 bytes, MD5 `2283abe6d5105dc8564436c27c7d3d0b`, SHA256 `45b4eceda69f80a30a4ce349d0e9baefacace0de394fe315f3c392260ea8d418`.
- `softqp-coupled-study-v1.zip.sha256`: 94 bytes, MD5 `511dc897a92b265361aeecdc72e7c0ef`, SHA256 `925037cc1f48213a56a2e2c90a49a82af0f7402d0f8ec2fe07114fd2a4d763c0`.

Each size and hash was recomputed over every byte of a new unauthenticated streamed response. ZIP magic is correct; the checksum content names the exact approved ZIP and SHA256. These bytes match the separately accepted, fully decompressed and inventoried original archive, so that prior archive-content review applies to the published bytes. No new reoptimization or scientific replay was necessary. A second record/files read after both streams confirms metadata and inventory remained unchanged during verification.

The dataset publicly has IsSupplementTo report `10.5281/zenodo.23875072`. A fresh anonymous read confirms that report is published and has reciprocal IsSupplementedBy dataset `10.5281/zenodo.23875194`, retaining its exact one-PDF inventory. The report's full PDF bytes and metadata were independently accepted earlier in `public-report-review.json`; this fresh binding check supplements that receipt. These are distinct standalone manuscript and dataset concepts, not a new version of the old application report.

Delivered publisher source is the exact previously accepted timeout source `5091ba645a8468762c39df007c8b80a924d348bd6265e57b9c1b5d18e44e16c3`; the optional bucket prototype is absent from that delivered identity. Its separate mock-only review history and initial failures remain preserved. The reviewer did not infer throughput from progress counters and makes no speed claim for the upload transport.

Evidence: `public-dataset-check.py`, `public-dataset-checks.json`, public record/latest/files snapshots and after-stream snapshots. This attests public availability and exact evidence integrity at the observed time. Owner-side publication/verification completion is separately recorded by the author. The primary study criterion remains **NOT ESTABLISHED**; there is no operational-performance, qualified companion-app release, peer-review or algorithmic-priority acceptance.
