# Extrator SIGSIF — Streamlit

## O que faz
- Recebe o nome do país informado pelo usuário.
- Acessa o SIGSIF usando Playwright.
- Baixa o relatório PDF da área CARNE.
- Processa as páginas com PyMuPDF e pandas.
- Gera um Excel para download no navegador.

## Arquivos
- `app.py`: aplicação e lógica de extração.
- `requirements.txt`: bibliotecas Python.
- `packages.txt`: dependências de sistema tentativas para Chromium no Community Cloud.

## Testar localmente
1. Instale Python 3.11.
2. Abra o terminal nesta pasta.
3. Execute:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   streamlit run app.py
   ```

## Publicar no Streamlit Community Cloud
1. Crie um repositório GitHub e envie os três arquivos.
2. Acesse https://share.streamlit.io/ e entre com sua conta GitHub.
3. Escolha o repositório, a branch e o arquivo `app.py`.
4. Clique em Deploy.

## Observações importantes
- O app precisa de acesso à internet para consultar o SIGSIF.
- O projeto fixa o Playwright em uma versão que já foi usada em relatos de compatibilidade com o Community Cloud e tenta instalar o Chromium na primeira execução. Isso pode demorar ou falhar em hospedagem gratuita; se ocorrer, será necessário ajustar a configuração de sistema ou escolher outro host.
- A hospedagem gratuita pode ter limites de memória, tempo de execução e disponibilidade.
- O código de extração foi adaptado do script original, mas deve ser validado com PDFs reais de diferentes países antes de uso oficial.
- A extração de país usa correspondência exata ou parcial única. Se houver mais de um resultado semelhante, o app pede que o usuário informe o nome completo.
