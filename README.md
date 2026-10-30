# Agente de vestibulares - Vale do Ribeira

## Como colocar para rodar todo mês

1. Crie um repositório no GitHub (pode ser privado) e envie estes arquivos
   (mantenha a pasta `.github/workflows/`).
2. Pegue uma chave em https://console.anthropic.com e cadastre em
   **Settings > Secrets and variables > Actions > New repository secret**
   com o nome `ANTHROPIC_API_KEY`.
3. Vá em **Actions > Atualizar vestibulares > Run workflow** para testar.
4. Pronto: dia 1º de cada mês ele roda sozinho e atualiza
   `vestibulares.json`, `vestibulares.csv` e `index.html`.

Dica: ative o **GitHub Pages** no repositório para ter o `index.html`
como uma página pública sempre atualizada.

## Testar no seu computador

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python agente_vestibular.py
```

## Ajustes

- Edite `INSTITUICOES` para fixar as faculdades que você quer acompanhar.
- `DESCOBRIR=0` desliga a busca automática de novas instituições.
- Custo: algumas buscas por instituição por mês, normalmente centavos a poucos dólares.

## Limites

O agente lê páginas da web e pode errar ou não achar um edital. Cada linha traz
o link da fonte, e vale conferir no edital oficial antes de se inscrever.
