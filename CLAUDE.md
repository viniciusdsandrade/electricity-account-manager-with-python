# Electricity Account Manager

Ferramenta CLI que compara produção solar (CSV do inversor) vs consumo de energia (PDF da fatura CPFL) e gera relatórios mensais em CSV e PDF.

## Stack

- Python 3.12, sem framework web — CLI puro via `argparse`
- pandas para manipulação de dados, pdfplumber para leitura de PDFs, reportlab para geração de PDF
- Virtualenv em `.venv`

## Como rodar

```bash
source .venv/bin/activate
python cli.py                           # usa defaults de config.py
python cli.py --solar-csv <path> --bill-pdf <path>   # arquivos personalizados
```

## Convenções de código

- Todo módulo começa com `from __future__ import annotations`
- Dataclasses imutáveis (`frozen=True`) para configs e records
- Nomes de domínio em português (saldo_kwh, economia_imediata_r$, etc.)
- Parsers usam `@staticmethod` / `@classmethod` — sem instanciação
- Formatação numérica pt-BR: vírgula como separador decimal, ponto como separador de milhar

## Estrutura de dados

- `energy-bill/` — PDFs das faturas CPFL (entrada)
- `energy-production/` — CSVs do inversor solar (entrada)
- `report/` — relatórios gerados (saída)
- Caminhos default estão hardcoded em `config.py` com paths absolutos

## Commits

- Prefixos: `feat:` para funcionalidades, `report:` para arquivos de relatório gerados
- Mensagens em inglês

## Observações

- Não existem testes automatizados
- O parser CPFL (`src/parsers/cpfl_pdf.py`) usa regex específica para o layout de faturas da CPFL Paulista; pode não funcionar com outras distribuidoras
- O CSV do inversor segue formato `YYYY.M.D,produção,consumo` (exportação Hoymiles)
- `config.py` contém paths absolutos do ambiente local — ajustar ao mudar de máquina
