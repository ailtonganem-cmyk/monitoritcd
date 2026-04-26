"""Testes de regressão de prompt LLM (Sugestão #13).

Quando `PROMPT_VERSION` em `filters/llm_classifier.py` é alterada, esta suite
roda contra cassettes congelados e compara saída antiga vs nova. O dono
aprova diff manualmente — o objetivo é evitar drift silencioso de comportamento.
"""
