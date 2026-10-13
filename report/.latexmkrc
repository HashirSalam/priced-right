# latexmk configuration for the UH Data Science report template (LuaLaTeX + Biber, tagged PDF).
# Run from this directory: the class loads template/ files by relative path.
$pdf_mode = 4;
$lualatex = 'lualatex -interaction=nonstopmode -file-line-error -synctex=1 %O %S';
$out_dir = 'build';
@default_files = ('main.tex');
$bibtex_use = 2;
$clean_ext = 'synctex.gz synctex(busy) run.xml bbl bcf %R-luamml-mathml.html';
