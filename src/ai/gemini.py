from __future__ import annotations

import json
import warnings

import pandas as pd

from config import GeminiConfig
from parsers.cpfl_pdf import BillRecord, CpflPdfParser


def _get_client(config: GeminiConfig):
    """Create a Gemini client. Returns None if api_key is missing."""
    if config.api_key is None:
        return None
    from google import genai
    return genai.Client(api_key=config.api_key)


def _regex_fallback(text: str, source_pdf: str) -> BillRecord:
    """Full regex parsing path — mirrors CpflPdfParser.parse_bill_pdf logic."""
    month = CpflPdfParser.parse_reference_month(text)
    cons, inj = CpflPdfParser.parse_consumed_injected(text, month)
    if cons is None:
        raise ValueError(f"Regex fallback: não conseguiu extrair consumo do PDF: {source_pdf}")
    return BillRecord(
        month=month,
        consumption_kwh=int(cons),
        injected_kwh=int(inj) if inj is not None else None,
        source_pdf=source_pdf,
    )


_PARSE_PROMPT = """\
Você é um assistente especializado em extrair dados de faturas de energia elétrica brasileiras (CPFL).

Extraia do texto abaixo:
1. O mês/ano de referência da fatura
2. O consumo total em kWh
3. A energia ativa injetada em kWh (se houver)

Responda APENAS com JSON válido neste formato exato:
{"month": "YYYY-MM", "consumption_kwh": <int>, "injected_kwh": <int ou null>}

Texto da fatura:
"""


def parse_bill_text(text: str, source_pdf: str, config: GeminiConfig) -> BillRecord:
    """Parse bill text using Gemini AI, with regex fallback on failure."""
    client = _get_client(config)
    if client is None:
        warnings.warn("GEMINI_API_KEY não configurada. Usando parser regex.")
        return _regex_fallback(text, source_pdf)

    try:
        response = client.models.generate_content(
            model=config.model,
            contents=_PARSE_PROMPT + text,
        )
        raw = response.text.strip()
        # Remove markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)

        month = str(data["month"])
        consumption_kwh = int(data["consumption_kwh"])
        injected_raw = data.get("injected_kwh")
        injected_kwh = int(injected_raw) if injected_raw is not None else None

        return BillRecord(
            month=month,
            consumption_kwh=consumption_kwh,
            injected_kwh=injected_kwh,
            source_pdf=source_pdf,
        )
    except Exception as e:
        warnings.warn(f"Gemini parse falhou ({e}). Usando fallback regex.")
        return _regex_fallback(text, source_pdf)


_INSIGHTS_SHORT_PROMPT = """\
Você é um consultor de energia solar. Analise os dados abaixo e escreva um resumo curto \
(2-3 frases) em português do Brasil, destacando: economia obtida, saldo energético \
e se a produção solar foi suficiente para cobrir o consumo.
Use formato monetário brasileiro (R$ X.XXX,XX) e separador decimal com vírgula.

Dados do relatório:
"""

_INSIGHTS_DETAILED_PROMPT = """\
Você é um consultor de energia solar. Analise os dados abaixo e escreva uma análise \
detalhada em português do Brasil (1-2 parágrafos) contendo:
- Comparação entre produção e consumo
- Economia obtida e projeção de créditos
- Recomendações práticas para o consumidor
- Tendências observadas (se houver múltiplos meses)
Use formato monetário brasileiro (R$ X.XXX,XX) e separador decimal com vírgula.

Dados do relatório:
"""


def generate_insights(df: pd.DataFrame, config: GeminiConfig, detailed: bool = False) -> str:
    """Generate energy insights using Gemini AI. Returns empty string on failure."""
    client = _get_client(config)
    if client is None:
        warnings.warn("GEMINI_API_KEY não configurada. Insights indisponíveis.")
        return ""

    prompt = _INSIGHTS_DETAILED_PROMPT if detailed else _INSIGHTS_SHORT_PROMPT
    df_text = df.to_string(index=False)

    try:
        response = client.models.generate_content(
            model=config.model,
            contents=prompt + df_text,
        )
        return response.text.strip()
    except Exception as e:
        warnings.warn(f"Gemini insights falhou ({e}). Relatório gerado sem análise.")
        return ""
