# Source, data and manuscript licenses

The product's authored software is covered by [LICENSE](LICENSE). Third-party
material retains its own terms; a package dependency is not relicensed by this
repository.

| Material shipped here | Origin and modification | License and retained notice |
|---|---|---|
| `data-pipeline/pipeline/energy_reference.py` | OSQPSlack `energy_hub.py`, commit `2e5d5ce8968207d0838d08942a8af7bdda64f634`; attribution added and the penalty import redirected. Model constants and dynamics are unchanged. | MIT; [complete upstream notice](data/licenses/OSQPSlack-MIT.txt). |
| C13 model inputs, physical row metadata and numerical results in `data/derived/softqp/C13.json` | Computation from that attributed synthetic model, not an operational building dataset. | MIT source terms and attribution retained; authored numerical results follow the product license. |
| C14 and C15 model variants and results in `data/derived/softqp/` | The same attributed building structure with explicitly changed separable penalties. | MIT source terms and attribution retained; these are authored variants, not reproductions of the original objective. |
| Other case inputs and the sparse/two-zone coupled-study inputs | Authored synthetic mathematical problems and forecasts. No private customer or operational dataset is included. | Product-authored source/data follow the product license; the separately published evidence dataset states CC BY 4.0 for its data and retains source-code notices. |
| Manuscript text and manuscript figures in `manuscripts/` | Authored mathematical/computational reports and evidence-derived plots. | CC BY 4.0 for text and figures. Referenced software and sources retain their own licenses. |

The native `softqp` distribution is maintained in a separate repository. Its OSQP,
OSQPSlack and QDLDL notices accompany the published package; its source/license
inventory is not replaced by this product's license. Other pinned numerical and
frontend dependencies retain the licenses documented in their distributions and
the [framework cards](docs/frameworks/).

No learned model trained on third-party data is distributed. C13 attribution is
also shown in its case documentation and original result metadata. See
[attribution](ATTRIBUTION.md) and [the source comparison](docs/energy-provenance.md).
