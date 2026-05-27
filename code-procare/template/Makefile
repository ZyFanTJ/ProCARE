# 1. Detecta o único arquivo .tex na pasta
MAIN_TEX := $(wildcard *.tex)
FILENAME := $(basename $(MAIN_TEX))

# Extensões de arquivos temporários para limpeza
TEMP_EXTS := aux bbl blg log out toc fls fdb_latexmk snm nav xml bcf-stats.txt bcf synctex.gz

.DEFAULT_GOAL := help

# --- Alvos (Targets) ---

.PHONY: all clean distclean help compile

help: ## Exibe esta mensagem de ajuda
	@echo "Uso: make [alvo]"
	@echo ""
	@echo "Alvos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

all: compile clean ## Compila o LaTeX (latexmk ou manual) e limpa temporários logo após

compile: ## Apenas compila o documento (sem apagar temporários)
	@if [ -z "$(MAIN_TEX)" ]; then echo "Erro: Nenhum arquivo .tex encontrado."; exit 1; fi
	@if [ $(words $(MAIN_TEX)) -gt 1 ]; then echo "Erro: Mais de um arquivo .tex encontrado."; exit 1; fi
	@echo "Compilando: $(MAIN_TEX)..."
	@if command -v latexmk > /dev/null; then \
		latexmk -pdf -interaction=nonstopmode $(MAIN_TEX); \
	else \
		pdflatex -interaction=nonstopmode $(MAIN_TEX); \
		bibtex $(FILENAME); \
		pdflatex -interaction=nonstopmode $(MAIN_TEX); \
		pdflatex -interaction=nonstopmode $(MAIN_TEX); \
	fi

clean: ## Remove todos os arquivos temporários de compilação
	@echo "Limpando arquivos auxiliares..."
	@for ext in $(TEMP_EXTS); do rm -f *.$$ext; done

distclean: clean ## Remove temporários e também o arquivo PDF final
	@echo "Removendo PDF..."
	@rm -f $(FILENAME).pdf
