import pandas as pd
import pymupdf
import streamlit as st
import re
import zipfile
import gc
import os
from io import BytesIO

# --- Funções de Extração ---

@st.cache_data
def extrair_pdf(file_path_or_bytes: str | BytesIO, filename: str) -> dict:
    """
    Extrai dados específicos de um PDF do DETRAN-SP usando regex.
    
    Args:
        file_path_or_bytes: O caminho do arquivo (se salvo localmente) ou um objeto BytesIO.
        filename: O nome original do arquivo para incluir no resultado.
        
    Returns:
        Um dicionário com os dados extraídos.
    """
    data = {"Nome do Arquivo": filename}
    
    # pymupdf.open aceita o caminho do arquivo (str) ou o conteúdo (bytes)
    # Se for um BytesIO, precisamos ler o conteúdo em bytes.
    if isinstance(file_path_or_bytes, BytesIO):
        doc_content = file_path_or_bytes.read()
    else:
        doc_content = file_path_or_bytes # Assume que é o caminho (str)

    try:
        with pymupdf.open(stream=doc_content, filetype="pdf") as doc:
            text = chr(12).join([page.get_text() for page in doc])
            
            # 1. Delimitação do Texto Relevante
            find_comeco = text.find('Marca / Modelo')
            find_final = text.find('Este documento é fornecido exclusivamente para fins de conferência simples e não possui validade legal.')
            
            if find_comeco != -1 and find_final != -1:
                text = text[find_comeco:find_final]
            elif find_comeco != -1:
                text = text[find_comeco:]
            
            # 2. Limpeza de Padrões Irrelevantes
            pattern_link = r"https://www\.detran\.sp\.gov\.br/detransp/pb/servicos/veiculos/consultar_debitos_restricoes[/W?]id=consultar_debitos_restricoes"
            pattern_num = r"\d+/4"
            pattern_data_num = r"\d{2}/\d{2}/\d{4},\s+\d{2}:\d{2}"
            pattern_renavam_copy_icon = r"content_copy" # Assumindo ser um texto gerado pelo ícone

            text = re.sub(pattern_link, "", text)
            text = re.sub(pattern_num, "", text)
            text = re.sub(pattern_data_num, "", text)
            text = re.sub(pattern_renavam_copy_icon, "", text)

            # 3. Extração dos Campos com Regex
            
            match_marca = re.search(r"Marca / Modelo\s*(.*?)\s*Cor", text, re.DOTALL | re.IGNORECASE)
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

            # Débitos
            
            def clean_currency(match):
                """Função auxiliar para limpar e formatar valores monetários."""
                if match:
                    valor = match.group(1)
                    # Remove quebras de linha/espaços não-quebráveis (como \xa0)
                    return valor.strip().replace('\xa0', ' ').replace('\n', ' ')
                return None

            match_ipva = re.search(r"Total de débitos do IPVA\s*(R\$\s*[\d\.,\s]+)", text)
            data['Total IPVA'] = clean_currency(match_ipva)

            # Usa o padrão para 'Total de débitos que podem ser pagos com Pix'
            match_multas = re.search(r'Total de débitos que podem ser pagos com Pix\s*(R\$\s*[\d\.,\s]+)', text)
            data['Total Multas (Pix)'] = clean_currency(match_multas)
            
            # Tentativa de extrair 'Total de débitos fora do sistema estadual de multa'
            match_debitos_fora = re.search(r'Total de débitos fora do sistema estadual de multa\s*(R\$\s*[\d\.,\s]+)', text)
            if match_debitos_fora:
                data['Total de débitos fora do sistema estadual de multa'] = clean_currency(match_debitos_fora)
            else:
                 # Tentativa de extração alternativa se o valor não for R$
                 match_debitos_fora_alt = re.search(r'Total de débitos fora do sistema estadual de multa\s*(.*?)\s*Licenciamento', text, re.DOTALL | re.IGNORECASE)
                 if match_debitos_fora_alt:
                    data['Total de débitos fora do sistema estadual de multa'] = match_debitos_fora_alt.group(1).strip().replace('\n', ' ')

            # Licenciamento
            # Corrigido o regex para capturar melhor o valor de licenciamento
            match_ano = re.search(r"vencimento do licenciamento\s+(\d{2}/\d{2}/(\d{4}))", text, re.DOTALL | re.IGNORECASE)
            if match_ano:
                # Captura o grupo 2, que é o ano
                data['Ano Vencimento Licenciamento'] = match_ano.group(2)

            # 2. Extração do Valor
            # Procura por "Total de débitos" seguido imediatamente pelo padrão monetário (R$ com números).
            match_valor = re.search(r"Total de débitos\s*(R\$\s*[\d\.,]+)", text, re.DOTALL)
            if match_valor:
                data['Licenciamento - Total de débitos'] = match_valor.group(1).strip().replace('\n', ' ').replace('\xa0', ' ')

            # Restrições
            
            # Bloqueio de furto/roubo
            match_bloqueio_furto_roubo = re.search(r"Bloqueio de furto/roubo\s*(.*?)\s*Restrição tributária", text, re.DOTALL)
            if match_bloqueio_furto_roubo:
                data['Bloqueio de Furto/Roubo'] = match_bloqueio_furto_roubo.group(1).strip().replace('\n', ' ')

            # Restrição financeira
            match_restricao_financeira = re.search(r"Restrição financeira\s*(.*?)\s*Restrição\nadministrativa", text, re.DOTALL)
            if match_restricao_financeira:
                data['Restrição Financeira'] = match_restricao_financeira.group(1).strip().replace('\n', ' ').replace("Para liberar o pagamento do licenciamento, é preciso que todos os débitos do veículo tenham sido pagos.  Consultar Débitos e Restrições - Detran-SP  2/3", "").replace("Aviso sobre o pagamento do licenciamento Você só pode quitar um licenciamento por vez, começando pelo mais atrasado. Após fazer o pagamento, será exibido o próximo ano disponível para pagar, seguindo a ordem do mais antigo ao mais recente.  Consultar Débitos e Restrições - Detran-SP  2/3", "")
            
            # Restrição administrativa
            restricao_administrativa = re.search(r"Restrição\nadministrativa\s*(.*?)\s*Restrição judicial", text, re.DOTALL)
            if restricao_administrativa:
                data['Restrição Administrativa'] = restricao_administrativa.group(1).strip().replace('\n', ' ')
            
            # Restrição judicial
            # O padrão original é muito amplo: r"Restrição judicial\s*(.*?)\s*(.*?)\s*Restrição por veículo\nguinchado"
            # O primeiro grupo de captura (.*?) provavelmente pega o valor desejado.
            restricao_judicial = re.search(r"Restrição judicial\s*(.*?)\s*Restrição por veículo\nguinchado", text, re.DOTALL)
            if restricao_judicial:
                data['Restrição Judicial'] = restricao_judicial.group(1).strip().replace('\n', ' ')

            # Restrição por veículo guinchado - Adicionando por completude
            match_guinchado = re.search(r"Restrição por veículo\nguinchado\s*(.*?)\s*Restrição de gravame", text, re.DOTALL)
            if match_guinchado:
                data['Restrição por Veículo Guinchado'] = match_guinchado.group(1).strip().replace('\n', ' ')
        # st.cache_data retorna o valor final, neste caso, o dicionário.
        return data
    
    except Exception as e:
        return {"Nome do Arquivo": filename, "Erro": f"Falha na extração: {e}"}

# --- Streamlit UI ---

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
            df = df.fillna('Não informado')
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