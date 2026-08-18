import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

# Configuração da página
st.set_page_config(layout="wide", page_title="Inteligência COC")

# =========================================================
# 1. MOTOR DE DADOS (Conectado ao MySQL da Aiven)
# =========================================================
# ==========================================
st.set_page_config(
    page_title="Diretoria-COC",
    page_icon="logo.png", # Certifique-se de que o arquivo logo.png está na pasta raiz
    layout="wide"
)
# Função para criar a conexão com o banco
def get_engine():
    db = st.secrets["mysql"]
    url = f"mysql+pymysql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"
    return create_engine(url)

engine = get_engine()

# @st.cache_data(ttl=60) faz o Streamlit guardar os dados por 60 segundos 
# para não sobrecarregar o banco de dados se o usuário clicar muito rápido.
@st.cache_data(ttl=60)
def carregar_dados_diretoria():
    try:
        # 1. Puxa tudo da tabela planejamento_coc
        df = pd.read_sql("SELECT * FROM planejamento_coc", engine)
        
        # 2. Padroniza colunas (tudo minúsculo para evitar erros de leitura)
        df.columns = [str(c).lower() for c in df.columns]
        
        # 3. Renomeia as colunas do banco para os nomes que seus gráficos já usam
        df = df.rename(columns={
            'data_lançamento': 'Data Lançamento',
            'data_lancamento': 'Data Lançamento', 
            'classificação': 'Classificação',
            'classificacao': 'Classificação',
            'plano_de_contas': 'Plano de Contas',
            'itens': 'Itens',
            'valor_numerico': 'valor_final', # Caso sua coluna de valor se chame valor_numerico
            'valor_final': 'valor_final'     # Caso já se chame valor_final
        })
        
        # 4. Garante que os valores em dinheiro sejam números (float)
        df['valor_final'] = pd.to_numeric(df['valor_final'], errors='coerce').fillna(0.0)
        
        # 5. Garante que a data seja reconhecida e limpa dados vazios
        df["Data Lançamento"] = pd.to_datetime(df["Data Lançamento"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["Data Lançamento"])
        
        # Preenche textos vazios para o gráfico de Treemap não dar erro
        for col in ["Classificação", "Itens", "Plano de Contas"]:
            df[col] = df[col].fillna("Não Informado")
            
        return df

    except Exception as e:
        st.error(f"Erro ao conectar no banco de dados: {e}")
        # Retorna um DataFrame vazio com as colunas certas só para a tela não quebrar
        return pd.DataFrame(columns=["Data Lançamento", "Classificação", "Plano de Contas", "Itens", "valor_final"])

# Executa o carregamento
df = carregar_dados_diretoria()



# =========================================================
# 2. FILTROS NA SIDEBAR
# =========================================================
st.sidebar.header("📅 Filtros de Período")

data_min = df["Data Lançamento"].min().to_pydatetime()
data_max = df["Data Lançamento"].max().to_pydatetime()

periodo = st.sidebar.date_input("Selecione o Intervalo:", value=(data_min, data_max))

if isinstance(periodo, tuple) and len(periodo) == 2:
    data_inicio, data_fim = periodo
    df_filtrado = df[(df["Data Lançamento"].dt.date >= data_inicio) & 
                     (df["Data Lançamento"].dt.date <= data_fim)]
else:
    st.warning("Selecione o intervalo completo (início e fim).")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.header("🎯 Filtros de Análise")

# Escolha da Classificação
opcoes_classe = sorted(df_filtrado["Classificação"].unique())
classe_sel = st.sidebar.selectbox("1. Classificação:", opcoes_classe)

# Filtro de Plano de Contas
df_filtrado_classe = df_filtrado[df_filtrado["Classificação"] == classe_sel]
planos_disponiveis = sorted(df_filtrado_classe["Plano de Contas"].unique())
plano_sel = st.sidebar.multiselect("2. Plano de Contas:", planos_disponiveis)

# Filtro de Itens
if plano_sel:
    df_filtrado_plano = df_filtrado_classe[df_filtrado_classe["Plano de Contas"].isin(plano_sel)]
else:
    df_filtrado_plano = df_filtrado_classe

itens_disponiveis = sorted(df_filtrado_plano["Itens"].unique())
itens_sel = st.sidebar.multiselect("3. Itens (Para detalhamento):", itens_disponiveis)

# =========================================================
# =========================================================
# 3. EXIBIÇÃO DOS GRÁFICOS (ESTRUTURA FIXA + DINÂMICA)
# =========================================================
st.title("🧠 Inteligência Financeira - Análise Histórica")

# --- BLOCO 1: O MAPA DE QUADRADOS (TREEMAP) ---
# --- BLOCO 1: O MAPA DE QUADRADOS (TREEMAP) ---
st.subheader(f"🗺️ Mapa de Pesos: {classe_sel}")

if not df_filtrado_classe.empty:
    fig_tree = px.treemap(
        df_filtrado_classe, 
        path=['Plano de Contas', 'Itens'], 
        values='valor_final',
        color='valor_final',
        color_continuous_scale='Blues'
    )
    
    # É AQUI que definimos a altura para ele ficar "esticado" e bonito
    fig_tree.update_layout(
        margin=dict(t=30, l=10, r=10, b=10),
        height=500  # Ajuste esse número se quiser mais alto ou mais baixo
    )
    
    st.plotly_chart(fig_tree, use_container_width=True)

st.markdown("---")

# --- BLOCO 2: AS LINHAS TEMPORAIS (SÓ APARECEM AO FILTRAR) ---
if plano_sel:
    # Preparação dos dados temporais
    df_plano = df_filtrado_plano.copy()
    df_plano['Mes'] = df_plano['Data Lançamento'].dt.to_period('M').dt.to_timestamp()
    
    # Gráfico do Plano (Linha Única Grossa)
    st.subheader(f"📈 Evolução Consolidada: {', '.join(plano_sel)}")
    df_geral_timeline = df_plano.groupby('Mes')['valor_final'].sum().reset_index()
    
    fig_geral = px.bar(
        df_geral_timeline, 
        x="Mes", 
        y="valor_final",
        text_auto='.2s', # Mostra o valor em cima da barra
        template="plotly_white"
    )
    fig_geral.update_traces(marker_color='#2E86C1')
    st.plotly_chart(fig_geral, use_container_width=True)
    # Gráfico Detalhado (Aparece se escolher Itens)
    if itens_sel:
        st.markdown("---")
        st.subheader("🔍 Detalhamento por Item Selecionado")
        df_itens = df_plano[df_plano["Itens"].isin(itens_sel)].copy()
        df_itens_timeline = df_itens.groupby(['Mes', 'Itens'])['valor_final'].sum().reset_index()
        
        fig_detalhe = px.bar(
            df_itens_timeline, 
            x="Mes", 
            y="valor_final", 
            color="Itens", 
            barmode="group", # Coloca os itens lado a lado por mês
            text_auto='.2s'
        )
        st.plotly_chart(fig_detalhe, use_container_width=True)
else:
    # Mensagem amigável enquanto o usuário não escolhe o plano
    st.info("💡 O mapa acima mostra o todo. Para ver a **linha do tempo** de uma categoria, selecione um 'Plano de Contas' na lateral.")