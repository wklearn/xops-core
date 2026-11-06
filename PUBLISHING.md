# Publishing and safety checklist

This repository is an independent public reference implementation; it does not contain production XOps data or account credentials.

## Source release

- The default branch is public, with an MIT LICENSE.
- Review every future commit for secrets and personally identifiable information.
- Verify CI passes using the repository Actions tab.
- Do not push database files, old email records, API tokens, paid datasets or private project histories.
- For security reports, see [SECURITY.md](SECURITY.md).

## Local verification

```sh
python -m unittest discover -s tests -v
python -m xops_core init
python -m xops_core import examples/sample.json
python -m xops_core serve
```

Open http://127.0.0.1:8765/, approve the synthetic example and export with `python -m xops_core export approved.json`. Only synthetic test data should be used when publicly demonstrating the project.

## Roadmap

Potential future changes include importer compatibility adapters, evidence verification display, safe export workflows and easier Windows packaging. No automated posting is included in this release.
