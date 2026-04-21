# Makefile — Paper compilation
# Usage:
#   make cn       Compile Chinese version (requires xelatex + gbt7714)
#   make en       Compile English version (requires pdflatex)
#   make all      Compile both versions
#   make clean    Remove auxiliary files

XELATEX = xelatex
PDFLATEX = pdflatex
BIBTEX = bibtex

.PHONY: cn en all clean

all: cn en

cn: main_cn.pdf

en: main_en.pdf

main_cn.pdf: main_cn.tex references.bib
	$(XELATEX) -interaction=nonstopmode main_cn.tex
	$(BIBTEX) main_cn
	$(XELATEX) -interaction=nonstopmode main_cn.tex
	$(XELATEX) -interaction=nonstopmode main_cn.tex

main_en.pdf: main_en.tex references.bib
	$(PDFLATEX) -interaction=nonstopmode main_en.tex
	$(BIBTEX) main_en
	$(PDFLATEX) -interaction=nonstopmode main_en.tex
	$(PDFLATEX) -interaction=nonstopmode main_en.tex

clean:
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.lot *.lof *.synctex.gz
