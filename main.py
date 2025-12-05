import pandas as pd
import pymupdf
import streamlit as st
import re
import zipfile
import gc
from io import BytesIO
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
            try:
                valor = match_marca.group(1)
                data['Marca / Modelo'] = valor.replace("\n", " ")
            except:
                data['Marca / Modelo'] = valor
        
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

st.set_page_config(
    page_title="Extrator DETRAN-SP PDF",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗 Extrator de Dados de Débitos Veiculares (DETRAN-SP PDF)")
st.markdown("Faça o upload de um ou mais arquivos PDF (ou um arquivo ZIP) de consulta de débitos do DETRAN-SP para extrair os dados em uma tabela.")

# Widget de Upload
uploaded_files = st.file_uploader(
    "Selecione os arquivos PDF ou um arquivo ZIP",
    type=["pdf", "zip"],
    accept_multiple_files=True
)

if uploaded_files:
    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_files = 0
    
    # 1. Pré-processamento: Contar e extrair arquivos
    files_to_process = []
    
    for uploaded_file in uploaded_files:
        if uploaded_file.type == "application/zip":
            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    if member.filename.lower().endswith('.pdf'):
                        # Extrai para BytesIO para evitar salvar no disco
                        with zip_ref.open(member) as pdf_file:
                            pdf_bytes = BytesIO(pdf_file.read())
                            pdf_bytes.seek(0)
                            files_to_process.append((pdf_bytes, member.filename))
        elif uploaded_file.type == "application/pdf":
            files_to_process.append((uploaded_file, uploaded_file.name))

    total_files = len(files_to_process)
    
    if total_files == 0:
        st.warning("Nenhum arquivo PDF encontrado no upload. Certifique-se de que os arquivos PDF ou o ZIP contenham PDFs.")
    else:
        st.info(f"Processando {total_files} arquivo(s) PDF...")
        
        # 2. Processamento dos Arquivos
        for i, (file_content, filename) in enumerate(files_to_process):
            status_text.text(f"Extraindo dados de: {filename} ({i+1}/{total_files})")
            
            # A função extrair_pdf agora aceita o BytesIO ou o caminho (no Streamlit, passamos o objeto UploadedFile que se comporta como BytesIO)
            extracted_data = extrair_pdf(file_content, filename)
            all_data.append(extracted_data)
            
            progress_bar.progress((i + 1) / total_files)
            
            # Coletor de lixo para liberar memória
            gc.collect() 
        
        status_text.success("✅ Extração concluída!")
        progress_bar.empty()
        
        # 3. Exibição e Download
        if all_data:
            df = pd.DataFrame(all_data)
            
            # Reordenar colunas para melhor visualização
            default_cols = ["Nome do Arquivo", "Renavam", "Chassi", "Marca / Modelo", "Cor", "Ano fabricação", "Ano modelo", "Tipo", "Combustível"]
            debt_cols = [col for col in df.columns if "Total" in col or "débitos" in col or "Licenciamento" in col]
            restriction_cols = [col for col in df.columns if "Restrição" in col or "Bloqueio" in col]
            error_cols = [col for col in df.columns if "Erro" in col]
            
            # Cria a ordem final das colunas
            final_cols = [col for col in default_cols if col in df.columns]
            final_cols.extend([col for col in debt_cols if col not in final_cols])
            final_cols.extend([col for col in restriction_cols if col not in final_cols])
            final_cols.extend([col for col in error_cols if col not in final_cols])
            final_cols.extend([col for col in df.columns if col not in final_cols and col not in debt_cols and col not in restriction_cols and col not in error_cols])

            df = df[final_cols]
            
            st.subheader("Tabela de Dados Extraídos")
            st.dataframe(df)
            
            # Botão de Download
            csv_data = df.to_csv(index=False, sep=';', encoding='utf-8')
            
            st.download_button(
                label="⬇️ Baixar Tabela em CSV",
                data=csv_data,
                file_name='dados_detran_extraidos.csv',
                mime='text/csv'
            )

st.sidebar.header("Instruções")
st.sidebar.markdown(
    """
    1. **Faça o upload** dos arquivos PDF de consulta de débitos veiculares do DETRAN-SP.
    2. O sistema irá **extrair** as informações principais (Veículo, Débitos e Restrições) de cada PDF.
    3. Os resultados serão exibidos em uma **tabela**.
    4. Clique em **"Baixar Tabela em CSV"** para salvar os dados extraídos.
    """
)
