import streamlit as st
import pandas as pd
import httpx
import plotly.express as px
from datetime import datetime, timedelta
import io

# 1. FUNÇÕES DE BUSCA (API EBA v3 & SUPABASE)
def get_eba_data(data_inicio, data_fim):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {st.secrets['ACCESS_TOKEN']}",
        "client_token": st.secrets['CLIENT_TOKEN']
    }
    params = {
        "data_inicio": data_inicio.strftime('%Y-%m-%d'),
        "data_fim": data_fim.strftime('%Y-%m-%d')
    }
    try:
        with httpx.Client() as client:
            url = "https://api.eba.med.br/v3/consultas/buscaratendimentos"
            response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                resultado = response.json()
                return resultado.get("data", [])
            return []
    except:
        return []

def get_supabase_alerts():
    try:
        url = f"{st.secrets['SUPABASE_URL']}/rest/v1/transacoes?select=*"
        headers = {"apikey": st.secrets["SUPABASE_KEY"], "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}"}
        with httpx.Client() as client:
            r = client.get(url, headers=headers)
            return pd.DataFrame(r.json())
    except:
        return pd.DataFrame()

# 2. INTERFACE E LÓGICA DE AUDITORIA
st.title("🛡️ Central de Inteligência e Auditoria")

st.sidebar.header("📅 Filtro de Auditoria")

if 'data_inicio' not in st.session_state:
    st.session_state.data_inicio = datetime.now().date()
if 'data_fim' not in st.session_state:
    st.session_state.data_fim = datetime.now().date()

col_hoje, col_semana, col_mes = st.sidebar.columns(3)

if col_hoje.button("Hoje"):
    st.session_state.data_inicio = datetime.now().date()
    st.session_state.data_fim = datetime.now().date()

if col_semana.button("Semana"):
    st.session_state.data_inicio = (datetime.now() - timedelta(days=7)).date()
    st.session_state.data_fim = datetime.now().date()

if col_mes.button("Mês"):
    hoje = datetime.now().date()
    st.session_state.data_inicio = hoje.replace(day=1)
    prox_mes = (hoje.replace(day=28) + timedelta(days=4))
    st.session_state.data_fim = (prox_mes.replace(day=1) - timedelta(days=1))

d_ini = st.sidebar.date_input("Data Início:", value=st.session_state.data_inicio)
d_fim = st.sidebar.date_input("Data Fim:", value=st.session_state.data_fim)

st.session_state.data_inicio = d_ini
st.session_state.data_fim = d_fim

# --- BLOCO 2: MINERAÇÃO EBA ---
dados_eba = get_eba_data(d_ini, d_fim)

if dados_eba:
    lista_auditoria = []
    for at in dados_eba:
        at_id = at.get("atendimentoId") 
        paciente = at.get("pacienteNome")
        data_bruta = at.get("data") 
        anestesista = at.get("anestesistaNome")
        convenio = at.get("convenioNome")
        
        ids_procedimentos_vistos = set()

        # Varre equipes e procedimentos tratando possíveis retornos nulos
        equipes = at.get("equipes") or []
        for eq in equipes:
            procedimentos = eq.get("procedimentos") or []
            for pr in procedimentos:
                
                proc_id = pr.get("id")
                if not proc_id:
                    continue  # Pula se o procedimento não tiver ID válido
                
                if proc_id not in ids_procedimentos_vistos:
                    # Se 'procedimento' vier nulo, define como 'NÃO INFORMADO'
                    nome_procedimento = pr.get("procedimento") or "NÃO INFORMADO"
                    qtd = pr.get("quantidade", 1) 
                    
                    cobrado_unit = pr.get("valor")
                    produzido_unit = pr.get("valorCobrado")
                    
                    v_cobrado_total = (float(cobrado_unit) * qtd) if cobrado_unit else 0.0
                    v_produzido_total = (float(produzido_unit) * qtd) if produzido_unit else 0.0

                    lista_auditoria.append({
                        "Atendimento_ID": at_id,
                        "Paciente": paciente,
                        "Data": data_bruta,
                        "Anestesista": anestesista,
                        "Convenio": convenio,
                        "Procedimento": nome_procedimento,
                        "Qtd": qtd,
                        "Faturado": "Sim" if v_cobrado_total > 0 else "Não",
                        "V_Cobrado": v_cobrado_total,
                        "V_Produzido": v_produzido_total
                    })
                    
                    ids_procedimentos_vistos.add(proc_id)
    
    # Criando o DataFrame de forma segura
    if lista_auditoria:
        df = pd.DataFrame(lista_auditoria)
    else:
        # Garante estrutura mínima caso a lista esteja vazia
        df = pd.DataFrame(columns=["Atendimento_ID", "Paciente", "Data", "Anestesista", "Convenio", "Procedimento", "Qtd", "Faturado", "V_Cobrado", "V_Produzido"])

    # Tratamento seguro da coluna Procedimento (Garante que ela existe antes de tratar)
    if 'Procedimento' not in df.columns:
        df['Procedimento'] = "NÃO INFORMADO"
        
    df['Procedimento'] = df['Procedimento'].astype(str).str.upper().str.strip()
    
    # --- PROCESSAMENTO SEGURO ---
    df['V_Estimado'] = df.apply(lambda x: x['V_Cobrado'] if x['Faturado'] == "Sim" else x['V_Produzido'], axis=1)
    
    df['Paciente_ID'] = df['Paciente'].astype(str).str.lower().str.strip()
    df['Data_Dia'] = pd.to_datetime(df['Data']).dt.date 

    # Separação das bases
    df_financeiro = df.drop_duplicates(subset=['Atendimento_ID', 'Procedimento'])
    df_cirurgias = df.drop_duplicates(subset=['Paciente_ID', 'Data_Dia'])

    # --- KPIs ---
    c1, c2, c3= st.columns(3)
    
    valor_faturado = df_financeiro[df_financeiro['Faturado'] == 'Sim']['V_Cobrado'].sum()
    c1.metric("💰 Já Faturado", f"R$ {valor_faturado:,.2f}")
    
    pendentes = df_cirurgias[df_cirurgias['Faturado'] == 'Não'].shape[0]
    c2.metric("⏳ Cirurgias Pendentes", f"{pendentes}", delta="Fichas")
    
    c3.metric("🩺 Total de Cirurgias", len(df_cirurgias))

    

    # --- GRÁFICOS ---
    t1, t2, t3, t4 = st.tabs(["📊 Qtd por Convênio", "👨‍⚕️ Valor por Anestesista","📈 Qtd por Anestesista","Ticket Médio"])
    
    with t1:
        df_conv = df_cirurgias.groupby('Convenio').size().reset_index(name='Qtd')
        fig_qtd = px.bar(df_conv, x='Convenio', y='Qtd', text='Qtd', title="Cirurgias por Convênio")
        st.plotly_chart(fig_qtd, use_container_width=True)

    with t2:
        df_anes = df_financeiro.groupby('Anestesista')['V_Estimado'].sum().reset_index()
        fig_anes = px.bar(df_anes, x='Anestesista', y='V_Estimado', title="Produção por Médico (R$)")
        st.plotly_chart(fig_anes, use_container_width=True)
        
    with t3:
        df_vol_anes = df_cirurgias.groupby('Anestesista').size().reset_index(name='Total_Cirurgias')
        df_vol_anes = df_vol_anes.sort_values(by='Total_Cirurgias', ascending=False)
        
        fig_vol = px.bar(
            df_vol_anes, 
            x='Anestesista', 
            y='Total_Cirurgias', 
            text='Total_Cirurgias',
            title="Volume de Cirurgias por Médico",
            color_discrete_sequence=["#5dd2f0"]
        )
        st.plotly_chart(fig_vol, use_container_width=True)
    with t4:
        # Agrupa Valor Estimado
        df_anes_valor = df_financeiro.groupby('Anestesista')['V_Estimado'].sum().reset_index()
        
        # Agrupa Quantidade de Cirurgias do Médico
        df_anes_qtd = df_cirurgias.groupby('Anestesista').size().reset_index(name='Qtd_Cirurgias')
        
        # Faz o merge e calcula o Ticket Médio por Anestesista (Valor / Quantidade)
        df_anes = pd.merge(df_anes_valor, df_anes_qtd, on='Anestesista')
        df_anes['Ticket_Medio'] = df_anes['V_Estimado'] / df_anes['Qtd_Cirurgias']
        
        # Monta o gráfico exibindo o Ticket Médio e Qtd no Tooltip (hover)
        fig_anes = px.bar(
            df_anes, 
            x='Anestesista', 
            y='V_Estimado', 
            title="Produção e Ticket Médio por Médico (R$)",
            hover_data={
                "V_Estimado": ':,.2f',
                "Ticket_Medio": ':,.2f', 
                "Qtd_Cirurgias": True
            }
        )
        st.plotly_chart(fig_anes, use_container_width=True)
    # --- TABELA FINAL LIMPA ---
    st.subheader("📋 Detalhamento de Pendências")
    colunas_visiveis = ['Paciente', 'Anestesista', 'Convenio', 'Procedimento', 'V_Produzido']
    
    df_pendentes_tabela = df_financeiro[df_financeiro['Faturado'] == "Não"]
    
    if not df_pendentes_tabela.empty:
        st.dataframe(df_pendentes_tabela[colunas_visiveis], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma pendência encontrada para o período selecionado.")
        
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_financeiro.to_excel(writer, sheet_name='Conferir_Financeiro', index=False)
        df_cirurgias.to_excel(writer, sheet_name='Conferir_Fichas', index=False)

    buffer.seek(0)

    st.divider()
    st.subheader("📥 Exportar Dados para Auditoria")
    st.write("Baixe o arquivo para comparar os dados limpos do App com o relatório do seu sistema.")

    st.download_button(
        label="📊 Baixar Relatório Excel (Dados Limpos)",
        data=buffer,
        file_name=f"auditoria_limpa_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.warning("Nenhum dado encontrado na API do EBA para o período selecionado.")