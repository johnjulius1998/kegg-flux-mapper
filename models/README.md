# models/

Put your genome-scale metabolic models here. Every `*.xml` (SBML) file in this folder,
including sub-folders, appears in the app's model dropdown, labelled by its relative path.
JSON and MATLAB `.mat` models can be uploaded from the app instead.

Model files are not tracked by git (see `.gitignore`).

Good starting points are published models from [BiGG Models](http://bigg.ucsd.edu)
(e.g. `e_coli_core`) or a reconstruction built with ModelSEED, CarveMe or gapseq.
For pathway matching, reactions need `kegg.reaction` or `ec-code` annotations.

The test suite's characterization tests use `RehMBEL1391_sbml_L3V1.xml`; when that
file is absent, they are skipped.
