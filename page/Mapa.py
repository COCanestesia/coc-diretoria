import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import create_engine
from fpdf import FPDF # Caso você use para exportar futuramente

# ================================
# 0. CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA LINHA)
# ================================
st.set_page_config(page_title="Mapa Cirúrgico - COC", layout="wide")

# ================================
# 1. CONEXÃO MYSQL (AIVEN)
# ================================
@st.cache_resource
def conectar_banco():
    db_info = st.secrets["mysql"]
    conn_str = f"mysql+pymysql://{db_info['user']}:{db_info['password']}@{db_info['host']}:{db_info['port']}/{db_info['database']}"
    return create_engine(conn_str)

# ================================
# 2. PREPARAÇÃO DO DATAFRAME
# ================================
@st.cache_data(ttl=60)
def preparar_df_cirurgias():
    engine = conectar_banco()
    df = pd.read_sql("SELECT * FROM cirurgias", con=engine)
    
    df = df.rename(columns={
        "data_cirurgia": "DATA", "inicio": "INICIO", "termino": "TÉRMINO",
        "nome_paciente": "NOME DO PACIENTE", "idade": "IDADE", "procedimento": "PROCEDIMENTO",
        "sala": "SALA", "duracao": "DURAÇÃO", "cirurgiao": "CIRURGIÃO",
        "anestesista": "ANESTESISTA", "apoio": "APOIO", "tipo_anestesia": "TIPO DE ANESTESIA",
        "convenio": "CONVÊNIO", "acomodacao": "ACOMODAÇÃO", "hospital": "HOSPITAL",
        "status_check": "VALOR" # Certifique-se que o nome no banco é 'valor'
    })
    
    df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce").dt.strftime("%d/%m/%Y")
    # Garante que VALOR seja numérico
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0.0)
    df = df.fillna("")
    
    return df

# ================================
# 3. RENDERIZAÇÃO DO MAPA DIGITAL
# ================================
def renderizar_mapa_digital(df_cirurgias):
    st.title("GESTÃO COC ANESTESIA - MAPA")

    # Controle de Data via Session State
    if "data_mapa_view" not in st.session_state:
        st.session_state.data_mapa_view = date.today()

    def mudar_data(dias):
        st.session_state.data_mapa_view = date.today() + timedelta(days=dias)

    # Layout de Filtros
    c1, c2, c3, _ = st.columns([2, 1, 1, 4], vertical_alignment="bottom")
    data_mapa = c1.date_input("Selecione a Data", key="data_mapa_view")
    c2.button("Hoje", on_click=mudar_data, args=(0,), use_container_width=True)
    c3.button("Amanhã", on_click=mudar_data, args=(1,), use_container_width=True)

    data_str_mapa = data_mapa.strftime("%d/%m/%Y")
    df_dia = df_cirurgias[df_cirurgias["DATA"].astype(str) == data_str_mapa].copy()

    if not df_dia.empty:
        df_dia = df_dia.sort_values(by=["HOSPITAL", "SALA", "INICIO"])

        # Montagem do DataFrame Digital com VALOR no final
        df_digital = df_dia[[
            "INICIO", "TÉRMINO", "NOME DO PACIENTE", "IDADE", "PROCEDIMENTO", 
            "SALA", "DURAÇÃO", "CIRURGIÃO", "ANESTESISTA", "APOIO", 
            "TIPO DE ANESTESIA", "CONVÊNIO", "VALOR"
        ]].copy()
        
        df_digital.rename(columns={"INICIO": "HORÁRIO", "NOME DO PACIENTE": "PACIENTE"}, inplace=True)

        # Divisão por Turnos
        df_manha = df_digital[df_digital["HORÁRIO"] < "12:00"]
        df_tarde = df_digital[df_digital["HORÁRIO"] >= "12:00"]

        # --- EXIBIÇÃO DO MAPA ---
        st.subheader(f"📋 Mapa Cirúrgico - {data_str_mapa}")
        
        st.markdown("#### ☀️ MANHÃ")
        if not df_manha.empty:
            st.dataframe(df_manha, hide_index=True, use_container_width=True)
        else:
            st.info("Sem cirurgias para a manhã.")

        st.markdown("#### 🌇 TARDE / NOITE")
        if not df_tarde.empty:
            st.dataframe(df_tarde, hide_index=True, use_container_width=True)
        else:
            st.info("Sem cirurgias para a tarde/noite.")

        st.divider()

        # --- ANÁLISE DE PRODUÇÃO ---
        st.subheader("📊 Análise de Produção por Anestesista")
        
        # Criamos uma coluna de turno temporária para o cálculo
        df_digital["TURNO"] = df_digital["HORÁRIO"].apply(lambda x: "MANHÃ" if x < "12:00" else "TARDE/NOITE")
        
        # Tabela dinâmica (Pivot Table) para somar os valores
        analise = df_digital.pivot_table(
            index="ANESTESISTA", 
            columns="TURNO", 
            values="VALOR", 
            aggfunc="sum", 
            fill_value=0
        ).reset_index()

        # Garante que as duas colunas existam para não dar erro se não houver cirurgias num turno
        if "MANHÃ" not in analise.columns: analise["MANHÃ"] = 0.0
        if "TARDE/NOITE" not in analise.columns: analise["TARDE/NOITE"] = 0.0

        analise["TOTAL GERAL"] = analise["MANHÃ"] + analise["TARDE/NOITE"]
        analise = analise.sort_values("TOTAL GERAL", ascending=False)

        # Formatação para Moeda (R$)
        for col in ["MANHÃ", "TARDE/NOITE", "TOTAL GERAL"]:
            analise[col] = analise[col].apply(lambda x: f"R$ {x:,.2f}")

        st.dataframe(analise, hide_index=True, use_container_width=True)

    else:
        st.info("Nenhuma cirurgia encontrada para esta data.")

# ================================
# 4. EXECUÇÃO
# ================================
try:
    with st.spinner("Carregando dados..."):
        df_base = preparar_df_cirurgias()
    renderizar_mapa_digital(df_base)
except Exception as e:
    st.error(f"Ocorreu um erro: {e}")