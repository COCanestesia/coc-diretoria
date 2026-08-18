import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# --- CONEXÃO COM O BANCO ---
# (Se você já tiver a conexão global no seu app, pode apenas chamá-la aqui)
DB_USER = 'avnadmin'
DB_PASS = 'AVNS_tL8tlV93UQytgtReTi_'
DB_HOST = 'mysql-21ff11bc-thonydheque500-8de0.g.aivencloud.com'
DB_PORT = '12242'
DB_NAME = 'defaultdb'

@st.cache_resource
def get_connection():
    return create_engine(f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?ssl_disabled=False')

engine = get_connection()

# --- FUNÇÃO PARA CONVERTER TEMPO DO MYSQL PARA NÚMERO DECIMAL ---
def tempo_para_horas(tempo_str):
    if pd.isnull(tempo_str): return 0.0
    # Se vier como timedelta do banco
    if isinstance(tempo_str, pd.Timedelta):
        return tempo_str.total_seconds() / 3600.0
    # Se vier como string "HH:MM:SS"
    partes = str(tempo_str).split(':')
    if len(partes) >= 2:
        return int(partes[0]) + (int(partes[1]) / 60.0)
    return 0.0

# --- INTERFACE DA PÁGINA ---
st.title("📊 Relatório de Desempenho e Assiduidade")
st.markdown("Acompanhamento de pontualidade e banco de horas da equipe.")

# Controles de Filtro
col_mes_atual, col_mes_ant = st.columns(2)
with col_mes_atual:
    mes_atual = st.text_input("Competência Atual (ex: 06/2026)", value="06/2026")
with col_mes_ant:
    mes_anterior = st.text_input("Competência Anterior para Comparação (ex: 05/2026)", value="05/2026")

if st.button("Gerar Relatório"):
    with st.spinner("Analisando dados do banco..."):
        try:
            with engine.connect() as conn:
                query = text(f"""
                    SELECT d.nome, f.mes_ano, f.horas_trabalhadas, f.horas_extras, f.horas_atraso, f.horas_falta, d.equipe, d.turno 
                    FROM fato_consolidado_mensal f
                    JOIN dim_colaborador d ON f.id_colaborador = d.id_colaborador
                    WHERE f.mes_ano IN ('{mes_atual}', '{mes_anterior}')
                """)
                df = pd.read_sql(query, conn)
            
            if df.empty:
                st.warning(f"Nenhum dado encontrado para as competências informadas ({mes_atual} e {mes_anterior}).")
            else:
                # A MÁGICA ACONTECE AQUI: Soma as horas de Atraso e Falta em um único número decimal
                df['Atrasos (Dec)'] = df['horas_atraso'].apply(tempo_para_horas) + df['horas_falta'].apply(tempo_para_horas)
                df['Extras (Dec)'] = df['horas_extras'].apply(tempo_para_horas)
                
                # Separa os DataFrames por mês
                df_atual = df[df['mes_ano'] == mes_atual]
                df_anterior = df[df['mes_ano'] == mes_anterior]

                st.divider()

                # Trava caso o mês anterior não exista no banco
                if df_anterior.empty and not df_atual.empty:
                    st.info(f"💡 Nota: Ainda não temos dados da competência {mes_anterior}. A comparação mostrará apenas os volumes de {mes_atual}.")
                    total_atraso_ant = 0.0
                    total_extra_ant = 0.0
                else:
                    total_atraso_ant = df_anterior['Atrasos (Dec)'].sum()
                    total_extra_ant = df_anterior['Extras (Dec)'].sum()

                # --- 1. PAINEL DE COMPARAÇÃO GERAL (Voltou para 2 colunas) ---
                st.subheader("📈 Visão Geral da Clínica")
                
                total_atraso_atual = df_atual['Atrasos (Dec)'].sum()
                dif_atraso = total_atraso_atual - total_atraso_ant
                
                total_extra_atual = df_atual['Extras (Dec)'].sum()
                dif_extra = total_extra_atual - total_extra_ant

                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label=f"Total de Atrasos/Faltas ({mes_atual})", 
                        value=f"{total_atraso_atual:.1f}h", 
                        delta=f"{dif_atraso:.1f}h vs {mes_anterior}",
                        delta_color="inverse" 
                    )
                with col2:
                    st.metric(
                        label=f"Total de Extras ({mes_atual})", 
                        value=f"{total_extra_atual:.1f}h", 
                        delta=f"{dif_extra:.1f}h vs {mes_anterior}",
                        delta_color="normal"
                    )

                st.divider()

                # --- 2. RANKINGS DA EQUIPE NO MÊS ATUAL ---
                if not df_atual.empty:
                    st.subheader(f"🏆 Rankings de {mes_atual}")
                    col_rank1, col_rank2 = st.columns(2)

                    with col_rank1:
                        st.markdown("**Maiores Atrasos/Faltas** 🔴")
                        rank_atrasos = df_atual[['nome', 'horas_atraso', 'horas_falta', 'Atrasos (Dec)']].sort_values(by='Atrasos (Dec)', ascending=False)
                        rank_atrasos = rank_atrasos[rank_atrasos['Atrasos (Dec)'] > 0]
                        
                        if not rank_atrasos.empty:
                            # Mostramos as duas colunas na tela para o gestor saber o que é atraso e o que é falta inteira
                            st.dataframe(rank_atrasos[['nome', 'horas_atraso', 'horas_falta']].reset_index(drop=True), width='stretch')
                        else:
                            st.success("Nenhum atraso ou falta registrado na equipe neste mês!")

                    with col_rank2:
                        st.markdown("**Maiores Horas Extras** 🟢")
                        rank_extras = df_atual[['nome', 'horas_extras', 'Extras (Dec)']].sort_values(by='Extras (Dec)', ascending=False)
                        rank_extras = rank_extras[rank_extras['Extras (Dec)'] > 0]
                        
                        if not rank_extras.empty:
                            st.dataframe(rank_extras[['nome', 'horas_extras']].reset_index(drop=True), width='stretch')
                        else:
                            st.info("Nenhuma hora extra registrada neste mês.")

        except Exception as e:
            st.error(f"Erro ao gerar relatório: {e}")