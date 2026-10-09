# app.py

import datetime

import pandas as pd
import streamlit as st

from config import (
    C_CLUSTER, C_COD_CRM, C_DATA_ENCERR, C_DATA_FUND, C_DATA_TERRA,
    C_ID_EMP, C_LINHA, C_RESP1, C_SENIORIDADE,
    C_CIDADE, C_CIDADE_EMP, C_OBRA,
)
from core import (
    montar_linha,
    montar_output_empilhado,
    resolver_simultaneidade,
    sequenciar_linhas_existentes,
    sequenciar_novas_linhas,
)
from ui import (
    render_botao_iniciar,
    render_diagnostico,
    render_download,
    render_filtro_latencia,
    render_filtro_senioridade,
    render_filtro_distancia_cluster,
    render_guia_colunas,
    render_preview,
    render_resumo_parametros,
    render_resultado,
    render_upload,
)
from utils import (
    carregar_tabela_blindada,
    converter_data_mrv,
    obter_dicionario_coordenadas,
    validar_colunas,
)

st.set_page_config(page_title="Sequenciador de Obras - CB", layout="wide")
st.title("👷 Sequenciamento de Capacete Branco")
st.markdown("Faça o upload das duas planilhas abaixo para iniciar o sequenciamento automático de obras.")

render_guia_colunas()
st.divider()

arquivo_base, arquivo_empreendimentos = render_upload()

if not (arquivo_base and arquivo_empreendimentos):
    st.stop()

df_base = carregar_tabela_blindada(arquivo_base, "Base", "OBRA")
df_emp  = carregar_tabela_blindada(arquivo_empreendimentos, "Sheet1", "IDTRSICRM")

erros_base = validar_colunas(df_base, "Base")
erros_emp  = validar_colunas(df_emp,  "Sheet1")

if erros_base:
    st.error(f"❌ Colunas ausentes na guia 'Base': {', '.join(erros_base)}")
if erros_emp:
    st.error(f"❌ Colunas ausentes na guia 'Sheet1': {', '.join(erros_emp)}")
if erros_base or erros_emp:
    st.stop()

render_preview(df_base, df_emp)
render_diagnostico(df_base)

st.divider()

# ── Parâmetros ──────────────────────────────────────────────
render_filtro_latencia()          # mínima + máxima + sobreposição
render_filtro_senioridade()
render_filtro_distancia_cluster()

st.divider()

if not render_botao_iniciar():
    st.stop()

# ── Leitura dos snaps travados pelo botão ───────────────────
latencia_minima_meses      = st.session_state.get("snap_latencia_min",      2)
latencia_maxima_meses      = st.session_state.get("snap_latencia_max",      5)
sobreposicao_maxima_meses  = st.session_state.get("snap_sobreposicao",      0)
usar_senioridade           = st.session_state.get("snap_usar_senioridade",  True)
distancia_maxima_km        = st.session_state.get("snap_distancia_km",      75)
permitir_cluster_diferente = st.session_state.get("snap_permitir_cluster",  False)

# ── Conversão de datas ──────────────────────────────────────
for col in [C_DATA_FUND, C_DATA_TERRA, C_DATA_ENCERR]:
    if col in df_base.columns:
        df_base[col] = df_base[col].apply(converter_data_mrv)

for col in ["Fundação", "Terraplenagem", "Encerramento Módulo"]:
    if col in df_emp.columns:
        df_emp[col] = df_emp[col].apply(converter_data_mrv)

# ── Pré-processamento ───────────────────────────────────────
df_base[C_LINHA] = df_base.apply(montar_linha, axis=1)

nomes_base_completo = set(df_base[C_OBRA].dropna().astype(str).str.strip().unique())
ids_base_completo   = set(df_base[C_COD_CRM].dropna().astype(str).str.strip().unique())

df_base_repr, ids_devolvidos, info_devolvidas = resolver_simultaneidade(df_base)

cidades_unicas = list(
    set(df_base_repr[C_CIDADE].dropna().unique()) |
    set(df_emp[C_CIDADE_EMP].dropna().unique())
)
coord_cache = obter_dicionario_coordenadas(tuple(sorted(cidades_unicas)))

# ── Sequenciamento ──────────────────────────────────────────
df_base_repr, obras_alocadas, nomes_dh_alocados = sequenciar_linhas_existentes(
    df_base_repr, df_emp, coord_cache, info_devolvidas,
    latencia_minima_dias       = latencia_minima_meses * 30,
    latencia_maxima_dias       = latencia_maxima_meses * 30,
    sobreposicao_maxima_dias   = sobreposicao_maxima_meses * 30,
    nomes_base_completo        = nomes_base_completo,
    ids_base_completo          = ids_base_completo,
    usar_senioridade           = usar_senioridade,
    distancia_maxima_km        = distancia_maxima_km,
    permitir_cluster_diferente = permitir_cluster_diferente,
)

df_novas_linhas = sequenciar_novas_linhas(
    df_emp, coord_cache, obras_alocadas, info_devolvidas,
    latencia_minima_dias     = latencia_minima_meses * 30,
    latencia_maxima_dias     = latencia_maxima_meses * 30,
    sobreposicao_maxima_dias = sobreposicao_maxima_meses * 30,
    nomes_dh_alocados        = nomes_dh_alocados,
    distancia_maxima_km      = distancia_maxima_km,
)

mapa_emp  = df_emp.set_index(C_ID_EMP).to_dict(orient="index")
df_output = montar_output_empilhado(
    df_base_repr, info_devolvidas, df_novas_linhas, mapa_emp
)

st.divider()
st.success("✅ Sequenciamento concluído!")
render_resumo_parametros()
st.divider()
render_resultado(df_output)
st.divider()
render_download(df_output, df_emp)
