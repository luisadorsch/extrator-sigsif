# Copyright (c) 2026 Luísa Dorsch Ferreira
# Projeto: Extrator de dados do SIGSIF
# Finalidade: extração, organização e exportação de informações para Excel.
# Aplicação: https://habilitados-pais.streamlit.app/

import asyncio
import os
import re
import tempfile
import subprocess
import sys
from pathlib import Path

import fitz
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright

URL_SIGSIF = (
    "https://sigsif.agricultura.gov.br/"
    "sigsif_cons/%21ap_exportador_nac_pais_rep_net"
)
VALOR_AREA_CARNE = "1"


def normalizar_texto(texto):
    return re.sub(r"\s+", " ", texto).strip()


def eh_sif(texto):
    return bool(re.fullmatch(r"\d{1,5}", texto.strip()))


def eh_data(texto):
    return bool(re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto.strip()))


def localizar_sifs(page):
    palavras = page.get_text("words")
    sifs = []
    for w in palavras:
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 220 <= x0 <= 260 and eh_sif(texto):
            sifs.append({"sif": texto.strip(), "y": y0})
    return sorted(sifs, key=lambda x: x["y"])


def extrair_estabelecimento(page, y_inicio, y_fim):
    partes = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 55 <= x0 < 220 and y_inicio - 1 <= y0 < y_fim - 1:
            partes.append(w)
    partes.sort(key=lambda x: (x[1], x[0]))
    return normalizar_texto(" ".join(w[4] for w in partes))


def extrair_municipio(page, y_inicio, y_fim):
    partes = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 295 <= x0 < 410 and y_inicio - 1 <= y0 < y_fim - 1:
            partes.append(w)
    partes.sort(key=lambda x: (x[1], x[0]))
    return normalizar_texto(" ".join(w[4] for w in partes))


def extrair_uf(page, y_inicio, y_fim):
    partes = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 260 <= x0 < 295 and y_inicio - 1 <= y0 < y_fim - 1:
            partes.append(w)
    partes.sort(key=lambda x: (x[1], x[0]))
    return normalizar_texto(" ".join(w[4] for w in partes))


def localizar_produtos(page):
    palavras = page.get_text("words")
    linhas = {}
    for w in palavras:
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 400 <= x0 < 650 and 100 <= y0 <= 560:
            chave = (bloco, linha)
            if chave not in linhas:
                linhas[chave] = {"bloco": bloco, "linha": linha, "y": y0, "palavras": []}
            linhas[chave]["palavras"].append(w)

    linhas_ordenadas = sorted(linhas.values(), key=lambda x: x["y"])
    linhas_texto = []
    for item in linhas_ordenadas:
        palavras_linha = sorted(item["palavras"], key=lambda x: x[0])
        texto = normalizar_texto(" ".join(w[4] for w in palavras_linha))
        if texto:
            linhas_texto.append({
                "texto": texto, "y": item["y"],
                "bloco": item["bloco"], "linha": item["linha"]
            })

    produtos = []
    produto_atual = None
    bloco_atual = None
    for linha in linhas_texto:
        texto = linha["texto"]
        bloco = linha["bloco"]
        if bloco != bloco_atual:
            if produto_atual is not None:
                produtos.append(produto_atual)
            produto_atual = {
                "produto": texto, "y": linha["y"],
                "data_validade": "", "data_suspensao": ""
            }
            bloco_atual = bloco
            continue
        if texto.upper().startswith("PRODUTOS"):
            if produto_atual is not None:
                produtos.append(produto_atual)
            produto_atual = {
                "produto": texto, "y": linha["y"],
                "data_validade": "", "data_suspensao": ""
            }
        elif produto_atual is not None:
            produto_atual["produto"] = normalizar_texto(produto_atual["produto"] + " " + texto)

    if produto_atual is not None:
        produtos.append(produto_atual)
    return produtos


def localizar_datas(page):
    validades, suspensoes = [], []
    for w in page.get_text("words"):
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if not eh_data(texto) or y0 < 100 or y0 > 560:
            continue
        cx = (x0 + x1) / 2
        if 650 <= cx <= 720:
            validades.append({"data_validade": texto.strip(), "y": y0})
        elif 740 <= cx <= 800:
            suspensoes.append({"data_suspensao": texto.strip(), "y": y0})
    return {
        "validades": sorted(validades, key=lambda x: x["y"]),
        "suspensoes": sorted(suspensoes, key=lambda x: x["y"])
    }


def extrair_texto_produto(page, y_inicio, y_fim):
    partes = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, texto, bloco, linha, palavra = w
        if 400 <= x0 < 650 and y_inicio - 1 <= y0 < y_fim:
            partes.append(w)
    partes.sort(key=lambda x: (x[1], x[0]))
    return normalizar_texto(" ".join(w[4] for w in partes))


def processar_pagina(page, numero_pagina):
    sifs = localizar_sifs(page)
    produtos = localizar_produtos(page)
    datas = localizar_datas(page)
    validades, suspensoes = datas["validades"], datas["suspensoes"]

    for produto in produtos:
        candidatas = [d for d in validades if abs(d["y"] - produto["y"]) <= 5]
        if candidatas:
            produto["data_validade"] = min(candidatas, key=lambda d: abs(d["y"] - produto["y"]))["data_validade"]
        candidatas = [d for d in suspensoes if abs(d["y"] - produto["y"]) <= 5]
        if candidatas:
            produto["data_suspensao"] = min(candidatas, key=lambda d: abs(d["y"] - produto["y"]))["data_suspensao"]

    registros = []
    for i, registro_sif in enumerate(sifs):
        sif, y_sif = registro_sif["sif"], registro_sif["y"]
        y_proximo_sif = sifs[i + 1]["y"] if i + 1 < len(sifs) else 560
        estabelecimento = extrair_estabelecimento(page, y_sif, y_proximo_sif)
        municipio = extrair_municipio(page, y_sif, y_proximo_sif)
        uf = extrair_uf(page, y_sif, y_proximo_sif)

        produtos_sif = []
        for j, produto in enumerate(produtos):
            y_produto = produto["y"]
            if y_produto <= y_sif or y_produto >= y_proximo_sif:
                continue
            y_proximo_produto = produtos[j + 1]["y"] if j + 1 < len(produtos) else y_proximo_sif
            y_fim = min(y_proximo_produto, y_proximo_sif)
            texto_produto = extrair_texto_produto(page, y_produto, y_fim)
            if texto_produto:
                produtos_sif.append({
                    "produto": texto_produto,
                    "dt_validade": produto["data_validade"],
                    "dt_suspensao": produto["data_suspensao"]
                })

        for produto in produtos_sif:
            registros.append({
                "Página": numero_pagina,
                "S.I.F.": sif,
                "Estabelecimento": estabelecimento,
                "UF": uf,
                "Município": municipio,
                "Produto": produto["produto"],
                "Dt. Validade": produto["dt_validade"],
                "Dt. Suspensão": produto["dt_suspensao"]
            })
    return registros


@st.cache_resource(show_spinner="Preparando o navegador na primeira execução...")
def preparar_chromium():
    # O ambiente hospedado pode não ter o navegador do Playwright instalado.
    # Esta etapa pode demorar na primeira execução.
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        capture_output=True,
        text=True,
        timeout=240
    )
    return True


async def baixar_pdf_sigsif(pais_escolhido, diretorio):
    preparar_chromium()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            await page.goto(URL_SIGSIF, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            campo_pais = page.locator('select[name="p_id_pais"]')
            await campo_pais.wait_for(state="visible", timeout=60000)
            opcoes = campo_pais.locator("option")
            quantidade_opcoes = await opcoes.count()
            busca = pais_escolhido.strip().upper()
            candidatos = []

            for i in range(quantidade_opcoes):
                opcao = opcoes.nth(i)
                texto = (await opcao.inner_text()).strip()
                valor = await opcao.get_attribute("value")
                if texto and valor:
                    if texto.upper() == busca:
                        candidatos = [(texto, valor)]
                        break
                    if busca in texto.upper():
                        candidatos.append((texto, valor))

            if not candidatos:
                raise ValueError(f"País '{pais_escolhido}' não encontrado no SIGSIF.")
            if len(candidatos) > 1:
                opcoes_texto = ", ".join(texto for texto, _ in candidatos[:10])
                raise ValueError(
                    "O nome informado corresponde a mais de uma opção no SIGSIF. "
                    f"Digite o nome completo. Opções encontradas: {opcoes_texto}"
                )

            pais_atual, valor_pais = candidatos[0]
            await campo_pais.select_option(value=valor_pais)
            await page.wait_for_timeout(2000)

            campo_area = page.locator('select[name="p_id_area"]')
            await campo_area.wait_for(state="visible", timeout=60000)
            await campo_area.select_option(value=VALOR_AREA_CARNE)
            await page.wait_for_timeout(2000)

            botao_relatorio = page.locator('input[name="consultar"]')
            await botao_relatorio.wait_for(state="visible", timeout=30000)
            async with page.expect_download(timeout=60000) as download_info:
                await botao_relatorio.click()
            download = await download_info.value

            nome_pdf = "MAPA_" + re.sub(r'[\\/:*?"<>|]', "-", pais_atual) + ".pdf"
            caminho_pdf = os.path.join(diretorio, nome_pdf)
            await download.save_as(caminho_pdf)
            return caminho_pdf, pais_atual
        finally:
            await browser.close()


def gerar_excel(caminho_pdf, pais_atual):
    todos_registros = []
    with fitz.open(caminho_pdf) as doc:
        total_paginas = len(doc)
        progresso = st.progress(0, text="Processando PDF...")
        for i, page in enumerate(doc, start=1):
            todos_registros.extend(processar_pagina(page, i))
            progresso.progress(i / max(total_paginas, 1), text=f"Processando página {i} de {total_paginas}...")
        progresso.empty()

    colunas = [
        "Página", "S.I.F.", "Estabelecimento", "UF", "Município",
        "Produto", "Dt. Validade", "Dt. Suspensão"
    ]
    df = pd.DataFrame(todos_registros, columns=colunas)
    nome_excel = "MAPA_" + re.sub(r'[\\/:*?"<>|]', "-", pais_atual) + "_produtos_autorizados.xlsx"
    caminho_excel = os.path.join(os.path.dirname(caminho_pdf), nome_excel)
    with pd.ExcelWriter(caminho_excel, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Dados", index=False)
    return df, caminho_excel, nome_excel


st.set_page_config(page_title="Extrator SIGSIF", page_icon="📊", layout="centered")
st.title("📊 Extrator SIGSIF")
st.caption("Consulta de estabelecimentos e produtos autorizados para exportação")

st.markdown(
    "Selecione o país para consultar o SIGSIF. O sistema baixará o relatório PDF, "
    "processará os registros e preparará uma planilha Excel para download."
)

pais = st.text_input(
    "País de destino",
    placeholder="Digite o nome do país exatamente como aparece no SIGSIF",
    help="Se houver países com nomes semelhantes, informe o nome completo para evitar ambiguidades."
)

st.info("Área consultada: CARNE")

if st.button("🔎 Extrair dados e gerar Excel", type="primary", use_container_width=True):
    if not pais.strip():
        st.warning("Digite o nome do país antes de iniciar a extração.")
    else:
        with st.status("Iniciando extração...", expanded=True) as status:
            try:
                st.write("Acessando o SIGSIF e localizando o país...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    caminho_pdf, pais_atual = asyncio.run(baixar_pdf_sigsif(pais, temp_dir))
                    st.write(f"Relatório obtido para: **{pais_atual}**")
                    st.write("Transformando o PDF em uma planilha Excel...")
                    df, caminho_excel, nome_excel = gerar_excel(caminho_pdf, pais_atual)

                    if df.empty:
                        st.warning("O PDF foi processado, mas nenhum registro foi extraído. Confira o relatório e as regras de extração.")
                    else:
                        st.success(f"Extração concluída: {len(df):,} registros encontrados.")
                        st.dataframe(df.head(30), use_container_width=True)
                        with open(caminho_excel, "rb") as f:
                            excel_bytes = f.read()
                        st.download_button(
                            "⬇️ Baixar Excel",
                            data=excel_bytes,
                            file_name=nome_excel,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    status.update(label="Processamento finalizado", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Não foi possível concluir a extração", state="error", expanded=True)
                st.error(str(e))
                st.info("Se o erro persistir, pode ser uma mudança no SIGSIF, indisponibilidade do site ou limitação do ambiente de hospedagem.")
st.caption("Ferramenta de apoio. Confira os dados extraídos antes de utilizá-los em documentos oficiais.")
