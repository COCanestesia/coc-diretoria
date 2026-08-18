import pandas as pd
import httpx
from datetime import datetime
import streamlit as st # Usaremos apenas para acessar os secrets

# --- CONFIGURAÇÃO DO PERÍODO ---
DATA_INICIO = "2026-04-27"
DATA_FIM = "2026-05-04"

def buscar_dados_brutos():
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {st.secrets['ACCESS_TOKEN']}",
        "client_token": st.secrets['CLIENT_TOKEN']
    }
    params = {
        "data_inicio": DATA_INICIO,
        "data_fim": DATA_FIM
    }
    
    print(f"Buscando dados de {DATA_INICIO} até {DATA_FIM}...")
    
    try:
        with httpx.Client(timeout=60.0) as client:
            url = "https://api.eba.med.br/v3/consultas/buscaratendimentos"
            response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json().get("data", [])
            else:
                print(f"Erro API: {response.status_code}")
                return []
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return []

def gerar_relatorio_detalhado():
    dados = buscar_dados_brutos()
    
    if not dados:
        print("Nenhum dado encontrado para o período.")
        return

    lista_para_excel = []

    for at in dados:
        # Informações básicas do atendimento
        at_id = at.get("id")
        paciente = at.get("pacienteNome")
        data_atend = at.get("data")
        convenio = at.get("convenioNome")
        medico = at.get("anestesistaNome")

        # Explorar cada procedimento para ver por que o valor diverge
        for eq in at.get("equipes", []):
            for pr in eq.get("procedimentos", []):
                v_cobrado = float(pr.get("valor") or 0)
                v_produzido = float(pr.get("valorCobrado") or 0)
                
                lista_para_excel.append({
                    "ID_Atendimento": at_id,
                    "Data": data_atend,
                    "Paciente": paciente,
                    "Convenio": convenio,
                    "Anestesista": medico,
                    "Procedimento": pr.get("procedimento"),
                    "Valor_No_XML_Cobrado": v_cobrado,
                    "Valor_Produzido_Estimado": v_produzido,
                    "Status_Faturado": "Sim" if v_cobrado > 0 else "Não",
                    "Diferenca": v_produzido - v_cobrado
                })

    # Criar DataFrame
    df = pd.DataFrame(lista_para_excel)

    # Nome do arquivo com data para facilitar
    nome_arquivo = f"AUDITORIA_COC_{DATA_INICIO}_A_{DATA_FIM}.xlsx"
    
    # Exportar para Excel
    df.to_excel(nome_arquivo, index=False)
    print(f"✅ Sucesso! Arquivo gerado: {nome_arquivo}")
    print(f"Total de registros: {len(df)}")

if __name__ == "__main__":
    # Certifique-se de que o streamlit secrets está configurado ou 
    # substitua as chaves manualmente aqui para rodar como script puro.
    gerar_relatorio_detalhado()