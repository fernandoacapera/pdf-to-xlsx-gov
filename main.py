import pandas as pd
import pymupdf
import streamlit as st
import re
import zipfile
import gc
def extrair_pdf(pdf) -> list:
    data = {}
    with pymupdf.open('pdf/'+pdf) as doc:
        text = chr(12).join([page.get_text() for page in doc])
        find_comeco = text.find('Marca / Modelo')
        find_final = text.find('Este documento é fornecido exclusivamente para fins de conferência simples e não possui validade legal.')
        if find_comeco != -1:
            text = text[find_comeco:find_final]
        pattern_link = r"https://www.detran.sp.gov.br/detransp/pb/servicos/veiculos/consultar_debitos_restricoes[/W?]id=consultar_debitos_restricoes"
        pattern_num = r"\d+/4"
        pattern_data_num = r"\d{2}/\d{2}/\d{4},\s+\d{2}:\d{2}"
        pattern_renavam = r"content_copy"
        text = re.sub(pattern_link,"",text)
        text = re.sub(pattern_num,"", text)
        text = re.sub(pattern_data_num,"", text)
        text = re.sub(pattern_renavam,"", text)

        match_marca = re.search(r"Modelo\s*(.*?)\s*Cor", text, re.DOTALL | re.IGNORECASE)
        if match_marca:
            data['Marca / Modelo'] = match_marca.group(1).strip()
        
        match_cor = re.search(r"Cor\s*(\w+)", text, re.IGNORECASE)
        if match_cor:
            data['Cor'] = match_cor.group(1)
        
        match_renavam = re.search(r"Renavam\s*(\d{11})", text, re.IGNORECASE)
        if match_renavam:
            data["Renavam"] = match_renavam.group(1)

        match_ano_fab = re.search(r"Ano\s*fabricação\s*(\d{4})", text, re.IGNORECASE)
        if match_ano_fab:
            data['Ano fabricação'] = match_ano_fab.group(1)

        match_chassi = re.search(r"Chassi\s*([A-Z0-9]{17})", text, re.IGNORECASE)
        if match_chassi:
            data['Chassi'] = match_chassi.group(1)

        match_ano_mod = re.search(r"Ano\s*modelo\s*(\d{4})", text, re.IGNORECASE)
        if match_ano_mod:
            data['Ano modelo'] = match_ano_mod.group(1)

        match_tipo = re.search(r"Tipo\s*(.*?)\s*Combustível", text, re.DOTALL | re.IGNORECASE)
        if match_tipo:
            data['Tipo'] = match_tipo.group(1).strip()

        match_comb = re.search(r"Combustível\s*(\w+)", text, re.IGNORECASE)
        if match_comb:
            data['Combustível'] = match_comb.group(1)

        match_ipva = re.search(r"Total de débitos do IPVA\s*(R\$\s*[\d\.,]+)", text)
        if match_ipva:
            valor = match_ipva.group(1)
            try:
                data['Total IPVA'] = valor.replace('\xa0', ' ')
            except:
                data['Total IPVA'] = valor.group(1)
        
        match_multas = re.search(r'Total de débitos que podem ser pagos com Pix\s*(R\$\s*[\d\.,]+)', text)
        if match_multas:
            valor = match_multas.group(1)
            try:
                data['Total Multas'] = valor.replace('\xa0', ' ')
            except:
                data['Total Multas'] = valor.group(1)
        try:
            match_debitos_fora = re.search(r'Total de débitos fora do sistema estadual de multa\s*(R\$\s*[\d\.,]+)', text)
            if match_multas:
                valor = match_debitos_fora.group(1)
                try:
                    data['Total de débitos fora do sistema estadual de multa'] = valor.replace('\xa0', ' ')
                except:
                    data['Total de débitos fora do sistema estadual de multa'] = valor
        except:
            match_debitos_fora = re.search(r'Total de débitos fora do sistema estadual de multa\s*(.*?)\s*Licenciamento', text)
            if match_multas:
                data['Total de débitos fora do sistema estadual de multa'] = match_debitos_fora.group(1)   

        match_licenciamento = re.search(r"Total de débitos\s*(.*?)\s*Restrições do veículo", text)                                        
        if match_licenciamento:
            data['Licenciamento - Total de débitos'] = match_licenciamento.group(1)

        match_bloqueio_furto_roubo = re.search(r"Bloqueio de furto/roubo\s*(.*?)\s*Restrição tributária", text)
        if match_bloqueio_furto_roubo:
            data['Bloqueio de Furto/Roubo'] = match_bloqueio_furto_roubo.group(1)

        match_restricao_financeira = re.search(r"Restrição financeira\s*(.*?)\s*Restrição\nadministrativa", text)
        if match_restricao_financeira:
            data['Restrição Financeira'] = match_restricao_financeira.group(1)
        
        restricao_administrativa = re.search(r"Restrição\nadministrativa\s*(.*?)\s*Restrição judicial", text)
        if restricao_administrativa:
            data['Restrição Administrativa'] = restricao_administrativa.group(1)
        
        restricao_por_veiculo_guinchado = re.search(r"Restrição judicial\s*(.*?)\s*(.*?)\s*Restrição por veículo\nguinchado", text)
        if restricao_por_veiculo_guinchado:
            data['Restrição Judicial'] = restricao_por_veiculo_guinchado.group(1).strip()

    return [data]


st.set_page_config(page_title="PDF para EXCEL GOV", layout="wide")
st.title("Extrator de Dados de Veículos - GOV")
st.write("**OBS**: Caso seka muitos PDF's, transformar em ZIP")

uploades_files = st.file_uploader("Arraste seu PDF's ou arquivo ZIP aqui", tyé=['pdf', 'zip'], accept_multiple_files=True)

if uploades_files:
    if st.button("Iniciar Processamento"):
        
        dados_totais = []
        barra_progresso = st.progress(0)
        status_text = st.empty()
        
        total_arquivos_processados = 0
        
        # --- Lógica para lidar com ZIP ou PDFs soltos ---
        for i, file_obj in enumerate(uploades_files):
            
            # CASO 1: É um arquivo ZIP
            if file_obj.name.lower().endswith('.zip'):
                with zipfile.ZipFile(file_obj) as z:
                    # Filtra apenas arquivos PDF dentro do ZIP
                    lista_pdfs = [f for f in z.namelist() if f.lower().endswith('.pdf')]
                    total_zip = len(lista_pdfs)
                    
                    for k, nome_pdf in enumerate(lista_pdfs):
                        try:
                            status_text.text(f"Lendo do ZIP: {nome_pdf}")
                            # Lê o arquivo PDF específico dentro do ZIP (bytes)
                            pdf_bytes = z.read(nome_pdf)
                            
                            # Processa
                            linhas = extrair_pdf(pdf_bytes)
                            dados_totais.extend(linhas)
                            
                            # Libera memória
                            del pdf_bytes
                            if k % 50 == 0: gc.collect()
                            
                        except Exception as e:
                            st.error(f"Erro no arquivo {nome_pdf}: {e}")
            
            # CASO 2: É um arquivo PDF solto
            elif file_obj.name.lower().endswith('.pdf'):
                try:
                    status_text.text(f"Lendo arquivo: {file_obj.name}")
                    pdf_bytes = file_obj.read()
                    linhas = extrair_pdf(pdf_bytes)
                    dados_totais.extend(linhas)
                except Exception as e:
                    st.error(f"Erro ao ler {file_obj.name}: {e}")
            
            # Atualiza barra de progresso geral
            barra_progresso.progress((i + 1) / len(uploades_files))
            
        # --- Geração do Excel ---
        if dados_totais:
            linhas_ajustadas = []
            for linha in dados_totais:
                if len(linha) > len(COLUNAS):
                    linha = linha[:len(COLUNAS)]
                elif len(linha) < len(COLUNAS):
                    linha.extend(['Não informado'] * (len(COLUNAS) - len(linha)))
                linhas_ajustadas.append(linha)
            
            df = pd.DataFrame(linhas_ajustadas, columns=COLUNAS)
            
            st.success("Processamento concluído!")
            st.subheader("Prévia dos Dados")
            st.dataframe(df.head())
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Dados Veiculos')
                worksheet = writer.sheets['Dados Veiculos']
                for i, col in enumerate(df.columns):
                    worksheet.set_column(i, i, 20)
            
            st.download_button(
                label="Baixar Planilha",
                data=buffer,
                file_name="dados_veiculos_extraidos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Nenhum dado válido encontrado.")
