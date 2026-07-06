import datetime

import pandas as pd
import streamlit as st
from geopy.distance import geodesic

from config import (
    C_OBRA, C_COD_CRM, C_REGIONAL, C_CIDADE, C_CLUSTER,
    C_DATA_FUND, C_DATA_TERRA, C_DATA_ENCERR,
    C_COMPLEXIDADE_BASE, C_SENIORIDADE, C_LINHA, C_RESP1,
    C_ID_EMP, C_NOME_EMP, C_CIDADE_EMP, C_CLUSTER_EMP,
    C_FUND_EMP, C_TERRA_EMP, C_ENCERR_EMP, C_COMPLEXIDADE_EMP, C_REGIONAL_EMP,
    C_PROX_OBRA, C_ID_PROX, C_TERRA_PROX, C_ENCERR_PROX,
    C_CIDADE_PROX, C_ORIGEM, C_LATENCIA, C_DISTANCIA, C_FONTE_PROX,
)
from utils import sigla_senioridade, complexidades_permitidas_para, _normalizar


def montar_linha(row) -> str:
    cluster = str(row[C_CLUSTER]).strip()       if pd.notna(row[C_CLUSTER])    else ""
    sigla   = sigla_senioridade(row[C_SENIORIDADE])
    resp1   = str(row[C_RESP1]).strip().upper() if pd.notna(row[C_RESP1])      else ""
    partes  = [p for p in [cluster, sigla, resp1] if p != ""]
    return " | ".join(partes)


def resolver_simultaneidade(df_base):
    ids_devolvidos  = set()
    info_devolvidas = []
    indices_manter  = []

    for linha_id, grupo in df_base.groupby(C_LINHA):
        if len(grupo) == 1:
            indices_manter.append(grupo.index[0])
            continue
        grupo_valido = grupo[grupo[C_DATA_ENCERR].notna()]
        if grupo_valido.empty:
            indices_manter.append(grupo.index[0])
            continue
        idx_max = grupo_valido[C_DATA_ENCERR].idxmax()
        indices_manter.append(idx_max)
        for idx, row in grupo.iterrows():
            if idx == idx_max:
                continue
            cod = str(row.get(C_COD_CRM, "")).strip()
            if cod:
                ids_devolvidos.add(cod)
            info_devolvidas.append({
                "_idx_original": idx,
                "_linha_id":     linha_id,
                "_cod_crm":      cod,
                "_row":          row,
            })

    df_representantes = df_base.loc[indices_manter].copy()
    return df_representantes, ids_devolvidos, info_devolvidas


def _calcular_dist(cidade_a, cidade_b, coord_cache) -> float:
    ca = coord_cache.get(str(cidade_a)) if cidade_a else None
    cb = coord_cache.get(str(cidade_b)) if cidade_b else None
    if ca and cb:
        return geodesic(ca, cb).kilometers
    return 9999.0


def _filtrar_por_complexidade_dist_latencia(cands, permitidas, coord_atual,
                                             coord_cache, fim_atual,
                                             latencia_maxima_dias,
                                             distancia_maxima_km,
                                             sobreposicao_maxima_dias):
    if permitidas:
        cands = cands[cands["_complexidade_norm"].isin(permitidas)].copy()
    if cands.empty:
        return cands

    cands["_dist"] = cands[C_CIDADE_EMP].apply(
        lambda c: _calcular_dist(coord_cache.get(str(c)), coord_cache.get(str(c)), coord_cache)
        if not coord_atual else
        (geodesic(coord_atual, coord_cache.get(str(c))).kilometers
         if coord_cache.get(str(c)) else 9999.0)
    )
    cands = cands[cands["_dist"] <= distancia_maxima_km].copy()
    if cands.empty:
        return cands

    cands["_gap"] = (cands[C_TERRA_EMP] - fim_atual).dt.days
    cands = cands[
        (cands["_gap"] <= latencia_maxima_dias) &
        (cands["_gap"] >= -sobreposicao_maxima_dias)
    ].copy()

    return cands


def _buscar_em_linhas_existentes(df_candidatas, obras_alocadas,
                                  coord_cache, fim_atual, cid_atual, clu_atual,
                                  permitidas,
                                  distancia_maxima_km, latencia_maxima_dias,
                                  sobreposicao_maxima_dias,
                                  mesmo_cluster, permitir_sobreposicao):
    filtro_cluster = (
        df_candidatas[C_CLUSTER_EMP] == clu_atual
        if mesmo_cluster else
        df_candidatas[C_CLUSTER_EMP] != clu_atual
    )

    if permitir_sobreposicao:
        filtro_terra = (
            (df_candidatas[C_TERRA_EMP] >= fim_atual - pd.Timedelta(days=sobreposicao_maxima_dias)) &
            (df_candidatas[C_TERRA_EMP] < fim_atual)
        )
    else:
        filtro_terra = df_candidatas[C_TERRA_EMP] >= fim_atual

    cands = df_candidatas[
        filtro_terra &
        filtro_cluster &
        (~df_candidatas[C_ID_EMP].astype(str).str.strip().isin(obras_alocadas))
    ].copy()

    if cands.empty:
        return cands

    coord_atual = coord_cache.get(str(cid_atual)) if cid_atual else None
    sob_dias    = sobreposicao_maxima_dias if permitir_sobreposicao else 0

    cands = _filtrar_por_complexidade_dist_latencia(
        cands, permitidas, coord_atual, coord_cache,
        fim_atual, latencia_maxima_dias, distancia_maxima_km, sob_dias
    )

    return cands


def _buscar_em_novas_linhas(novas_linhas_dict, emp_row, coord_cache,
                             cluster_emp,
                             latencia_maxima_dias, sobreposicao_maxima_dias,
                             distancia_maxima_km,
                             mesmo_cluster, permitir_sobreposicao):
    melhor_key = None
    melhor_gap = None

    for key, info in novas_linhas_dict.items():
        if mesmo_cluster and info["cluster"] != cluster_emp:
            continue
        if not mesmo_cluster and info["cluster"] == cluster_emp:
            continue

        ultimo_encerr = info["ultimo_encerr"]
        if ultimo_encerr is None or pd.isna(ultimo_encerr):
            continue

        gap = (emp_row[C_TERRA_EMP] - ultimo_encerr).days

        if permitir_sobreposicao:
            if not (-sobreposicao_maxima_dias <= gap < 0):
                continue
        else:
            if not (0 <= gap <= latencia_maxima_dias):
                continue

        dist = _calcular_dist(info["ultima_cidade"], emp_row.get(C_CIDADE_EMP), coord_cache)
        if dist > distancia_maxima_km:
            continue

        if melhor_gap is None or gap < melhor_gap:
            melhor_gap = gap
            melhor_key = key

    return melhor_key, melhor_gap


def sequenciar_linhas_existentes(df_base_repr, df_emp, coord_cache, info_devolvidas,
                                  latencia_maxima_dias=90,
                                  sobreposicao_maxima_dias=0,
                                  nomes_base_completo=None,
                                  ids_base_completo=None,
                                  usar_senioridade=True,
                                  distancia_maxima_km=200,
                                  permitir_cluster_diferente=True):

    df_candidatas = df_emp[
        df_emp[C_TERRA_EMP].notna() &
        df_emp[C_ENCERR_EMP].notna() &
        df_emp[C_CIDADE_EMP].notna() &
        (df_emp[C_TERRA_EMP] >= pd.Timestamp(datetime.date.today()))
    ].copy()

    df_candidatas["_complexidade_norm"] = df_candidatas[C_COMPLEXIDADE_EMP].apply(
        lambda x: _normalizar(str(x).strip()) if pd.notna(x) and str(x).strip() != "" else ""
    )

    for col in [C_PROX_OBRA, C_ID_PROX, C_TERRA_PROX, C_ENCERR_PROX,
                C_CIDADE_PROX, C_ORIGEM, C_LATENCIA, C_DISTANCIA,
                C_FONTE_PROX, "Sobreposição"]:
        if col not in df_base_repr.columns:
            df_base_repr[col] = None

    ids_base = set(df_base_repr[C_COD_CRM].dropna().astype(str).str.strip().unique())
    if ids_base_completo:
        ids_base |= ids_base_completo

    mask_dh = df_base_repr[C_PROX_OBRA].notna() & (df_base_repr[C_PROX_OBRA].astype(str).str.strip() != "")
    df_base_repr.loc[mask_dh, C_FONTE_PROX]   = "DH"
    df_base_repr.loc[mask_dh, C_ORIGEM]        = "Sequenciamento DH"
    df_base_repr.loc[mask_dh, "Sobreposição"]  = "Não"

    obras_alocadas = set(df_base_repr[C_ID_PROX].dropna().astype(str).str.strip().unique())
    obras_alocadas |= ids_base

    nomes_dh = set(
        df_base_repr.loc[
            df_base_repr[C_PROX_OBRA].notna() &
            (df_base_repr[C_PROX_OBRA].astype(str).str.strip() != ""),
            C_PROX_OBRA
        ].astype(str).str.strip().unique()
    )
    ids_dh_por_nome = set(
        df_emp.loc[
            df_emp[C_NOME_EMP].astype(str).str.strip().isin(nomes_dh),
            C_ID_EMP
        ].astype(str).str.strip().unique()
    )
    obras_alocadas |= ids_dh_por_nome

    nomes_obra_a = set(df_base_repr[C_OBRA].dropna().astype(str).str.strip().unique())
    if nomes_base_completo:
        nomes_obra_a |= nomes_base_completo

    ids_obra_a_por_nome = set(
        df_emp.loc[
            df_emp[C_NOME_EMP].astype(str).str.strip().isin(nomes_obra_a),
            C_ID_EMP
        ].astype(str).str.strip().unique()
    )
    obras_alocadas |= ids_obra_a_por_nome

    df_candidatas = df_candidatas[
        ~df_candidatas[C_ID_EMP].astype(str).str.strip().isin(obras_alocadas)
    ].copy()

    barra      = st.progress(0)
    status_seq = st.empty()
    total      = len(df_base_repr)

    for idx, (i, row) in enumerate(df_base_repr.iterrows()):
        status_seq.text(f"🔄 Sequenciando linhas existentes: {row[C_OBRA]} ({idx+1}/{total})")
        barra.progress((idx + 1) / total)

        if pd.notna(row[C_PROX_OBRA]) and str(row[C_PROX_OBRA]).strip() != "":
            continue

        fim_atual = row[C_DATA_ENCERR]
        cid_atual = row[C_CIDADE]
        clu_atual = row[C_CLUSTER]
        sen_atual = row[C_SENIORIDADE]

        if pd.isna(fim_atual) or pd.isna(cid_atual) or pd.isna(clu_atual):
            continue

        permitidas = complexidades_permitidas_para(sen_atual) if usar_senioridade else set()

        resultado          = None
        cluster_diff       = False
        houve_sobreposicao = False

        tentativas = [
            (True,  False),
            (True,  True),
        ]
        if permitir_cluster_diferente:
            tentativas += [
                (False, False),
                (False, True),
            ]

        for mesmo_cluster, com_sobreposicao in tentativas:
            if com_sobreposicao and sobreposicao_maxima_dias == 0:
                continue

            cands = _buscar_em_linhas_existentes(
                df_candidatas, obras_alocadas,
                coord_cache, fim_atual, cid_atual, clu_atual,
                permitidas,
                distancia_maxima_km, latencia_maxima_dias,
                sobreposicao_maxima_dias,
                mesmo_cluster, com_sobreposicao
            )

            if not cands.empty:
                resultado          = cands.sort_values("_gap").iloc[0]
                cluster_diff       = not mesmo_cluster
                houve_sobreposicao = com_sobreposicao or (int(resultado["_gap"]) < 0)
                break

        if resultado is None:
            continue

        gap_resultado = int(resultado["_gap"])
        origem_seq = (
            "Sequenciamento - ferramenta (cluster diferente)"
            if cluster_diff else
            "Sequenciamento - ferramenta"
        )

        df_base_repr.at[i, C_PROX_OBRA]    = resultado[C_NOME_EMP]
        df_base_repr.at[i, C_ID_PROX]      = resultado[C_ID_EMP]
        df_base_repr.at[i, C_TERRA_PROX]   = resultado[C_TERRA_EMP]
        df_base_repr.at[i, C_ENCERR_PROX]  = resultado[C_ENCERR_EMP]
        df_base_repr.at[i, C_CIDADE_PROX]  = resultado[C_CIDADE_EMP]
        df_base_repr.at[i, C_ORIGEM]       = origem_seq
        df_base_repr.at[i, C_LATENCIA]     = gap_resultado
        df_base_repr.at[i, C_DISTANCIA]    = round(resultado["_dist"], 2)
        df_base_repr.at[i, C_FONTE_PROX]   = "Ferramenta"
        df_base_repr.at[i, "Sobreposição"] = "Sim" if houve_sobreposicao else "Não"
        obras_alocadas.add(str(resultado[C_ID_EMP]).strip())

    status_seq.empty()
    barra.empty()

    nomes_dh_alocados = set(
        df_base_repr.loc[
            df_base_repr[C_FONTE_PROX] == "DH",
            C_PROX_OBRA
        ].dropna().astype(str).str.strip().unique()
    )
    nomes_dh_alocados |= nomes_obra_a

    return df_base_repr, obras_alocadas, nomes_dh_alocados


def sequenciar_novas_linhas(df_emp, coord_cache, obras_alocadas, info_devolvidas,
                             latencia_maxima_dias=90,
                             sobreposicao_maxima_dias=0,
                             nomes_dh_alocados=None,
                             distancia_maxima_km=200,
                             permitir_cluster_diferente=False):

    if nomes_dh_alocados:
        ids_bloqueados_por_nome = set(
            df_emp.loc[
                df_emp[C_NOME_EMP].astype(str).str.strip().isin(nomes_dh_alocados),
                C_ID_EMP
            ].astype(str).str.strip().unique()
        )
        obras_alocadas |= ids_bloqueados_por_nome

    df_candidatas = df_emp[
        df_emp[C_TERRA_EMP].notna() &
        df_emp[C_ENCERR_EMP].notna() &
        df_emp[C_CIDADE_EMP].notna() &
        (df_emp[C_TERRA_EMP] >= pd.Timestamp(datetime.date.today()))
    ].copy()

    df_candidatas["_complexidade_norm"] = df_candidatas[C_COMPLEXIDADE_EMP].apply(
        lambda x: _normalizar(str(x).strip()) if pd.notna(x) and str(x).strip() != "" else ""
    )

    obras_nao_alocadas = df_candidatas[
        ~df_candidatas[C_ID_EMP].astype(str).str.strip().isin(obras_alocadas)
    ].copy()

    ids_devolvidos_validos = {
        d["_cod_crm"] for d in info_devolvidas
        if d["_cod_crm"]
        and d["_cod_crm"] not in obras_alocadas
        and str(d["_row"].get(C_OBRA, "")).strip() not in (nomes_dh_alocados or set())
    }

    if ids_devolvidos_validos:
        df_devolvidas_emp = df_emp[
            df_emp[C_ID_EMP].astype(str).str.strip().isin(ids_devolvidos_validos)
        ].copy()
        df_devolvidas_emp["_complexidade_norm"] = df_devolvidas_emp[C_COMPLEXIDADE_EMP].apply(
            lambda x: _normalizar(str(x).strip()) if pd.notna(x) and str(x).strip() != "" else ""
        )
        obras_nao_alocadas = pd.concat([df_devolvidas_emp, obras_nao_alocadas], ignore_index=True)
        obras_nao_alocadas = obras_nao_alocadas.drop_duplicates(subset=[C_ID_EMP])

    novas_linhas_rows     = []
    contador_novas_linhas = {}
    novas_linhas_dict     = {}

    if obras_nao_alocadas.empty:
        return pd.DataFrame(columns=[
            "Linha", "Ordem", "OBRA", "Cód. CRM", "Regional", "Cidade", "CLUSTER",
            "Complexidade Obra", "Data Fundação", "Data Terraplenagem",
            "Data Encerramento Módulo", "Fonte da Próxima Obra",
            "Origem Sequenciamento", "Latência (Dias)", "Distância (km)", "Sobreposição"
        ])

    st.info(f"🔁 {len(obras_nao_alocadas)} empreendimento(s) no pool — criando novas linhas por cluster...")

    obras_nao_alocadas_sorted = obras_nao_alocadas.sort_values(C_TERRA_EMP)
    barra2      = st.progress(0)
    status_seq2 = st.empty()
    total2      = len(obras_nao_alocadas_sorted)

    for idx2, (_, emp_row) in enumerate(obras_nao_alocadas_sorted.iterrows()):
        status_seq2.text(f"🆕 Criando novas linhas: {emp_row[C_NOME_EMP]} ({idx2+1}/{total2})")
        barra2.progress((idx2 + 1) / total2)

        cluster_emp = str(emp_row.get(C_CLUSTER_EMP, "")).strip()
        id_emp      = str(emp_row[C_ID_EMP]).strip()

        if id_emp in obras_alocadas:
            continue
        if nomes_dh_alocados and str(emp_row.get(C_NOME_EMP, "")).strip() in nomes_dh_alocados:
            continue

        linha_nova_key     = None
        melhor_gap         = None
        houve_sobreposicao = False

        tentativas = [
            (True,  False),
            (True,  True),
        ]
        if permitir_cluster_diferente:
            tentativas += [
                (False, False),
                (False, True),
            ]

        for mesmo_cluster, com_sobreposicao in tentativas:
            if com_sobreposicao and sobreposicao_maxima_dias == 0:
                continue

            key, gap = _buscar_em_novas_linhas(
                novas_linhas_dict, emp_row, coord_cache,
                cluster_emp,
                latencia_maxima_dias, sobreposicao_maxima_dias,
                distancia_maxima_km,
                mesmo_cluster, com_sobreposicao
            )

            if key is not None:
                linha_nova_key     = key
                melhor_gap         = gap
                houve_sobreposicao = com_sobreposicao or (gap is not None and gap < 0)
                break

        if linha_nova_key is None:
            if cluster_emp not in contador_novas_linhas:
                contador_novas_linhas[cluster_emp] = 0
            contador_novas_linhas[cluster_emp] += 1
            num            = contador_novas_linhas[cluster_emp]
            linha_nova_key = f"{cluster_emp} | Linha nova {num}"
            novas_linhas_dict[linha_nova_key] = {
                "cluster":       cluster_emp,
                "ultimo_encerr": None,
                "ultima_cidade": None,
                "ordem":         0,
            }
            houve_sobreposicao = False

        info          = novas_linhas_dict[linha_nova_key]
        ordem_emp     = info["ordem"] + 1
        ultimo_encerr = info["ultimo_encerr"]
        ultima_cidade = info["ultima_cidade"]

        if ultimo_encerr is not None and pd.notna(ultimo_encerr):
            gap_dias = (emp_row[C_TERRA_EMP] - ultimo_encerr).days
            dist_km  = round(_calcular_dist(ultima_cidade, emp_row.get(C_CIDADE_EMP), coord_cache), 2)
            flag_sob = "Sim" if gap_dias < 0 else "Não"
        else:
            gap_dias = None
            dist_km  = None
            flag_sob = "Não"

        novas_linhas_rows.append({
            "Linha":                    linha_nova_key,
            "Ordem":                    ordem_emp,
            "OBRA":                     emp_row.get(C_NOME_EMP),
            "Cód. CRM":                 emp_row.get(C_ID_EMP),
            "Regional":                 emp_row.get(C_REGIONAL_EMP),
            "Cidade":                   emp_row.get(C_CIDADE_EMP),
            "CLUSTER":                  cluster_emp,
            "Complexidade Obra":        emp_row.get(C_COMPLEXIDADE_EMP),
            "Data Fundação":            emp_row.get(C_FUND_EMP),
            "Data Terraplenagem":       emp_row.get(C_TERRA_EMP),
            "Data Encerramento Módulo": emp_row.get(C_ENCERR_EMP),
            "Fonte da Próxima Obra":    None,
            "Origem Sequenciamento":    "Sequenciamento - ferramenta",
            "Latência (Dias)":          gap_dias,
            "Distância (km)":           dist_km,
            "Sobreposição":             flag_sob,
        })

        novas_linhas_dict[linha_nova_key]["ultimo_encerr"] = emp_row[C_ENCERR_EMP]
        novas_linhas_dict[linha_nova_key]["ultima_cidade"] = emp_row.get(C_CIDADE_EMP)
        novas_linhas_dict[linha_nova_key]["ordem"]         = ordem_emp
        obras_alocadas.add(id_emp)

    barra2.empty()
    status_seq2.empty()

    return pd.DataFrame(novas_linhas_rows)


def montar_output_empilhado(df_base_repr, df_simultaneas, df_novas_linhas, mapa_emp, marco_inicio_obra_a):
    colunas_saida = [
        "Linha", "Tipo de Linha", "Ordem", "OBRA", "Cód. CRM", "Regional", "Cidade", "CLUSTER",
        "Complexidade Obra", "Senioridade ENG1",
        "Data Fundação", "Data Terraplenagem", "Data Encerramento Módulo",
        "Marco Início Obra A", "Simultaneidade",
        "Fonte da Próxima Obra", "Origem Sequenciamento",
        "Latência (Dias)", "Distância (km)", "Sobreposição",
    ]

    c_marco_base = C_DATA_TERRA if marco_inicio_obra_a == "Terraplenagem" else C_DATA_FUND
    linhas = []

    for _, row in df_base_repr.iterrows():
        linha_id    = row[C_LINHA]
        marco_valor = row.get(c_marco_base) if c_marco_base in df_base_repr.columns else None

        linhas.append({
            "Linha":                    linha_id,
            "Tipo de Linha":            "Existente",
            "Ordem":                    1,
            "OBRA":                     row.get(C_OBRA),
            "Cód. CRM":                 row.get(C_COD_CRM),
            "Regional":                 row.get(C_REGIONAL),
            "Cidade":                   row.get(C_CIDADE),
            "CLUSTER":                  row.get(C_CLUSTER),
            "Complexidade Obra":        row.get(C_COMPLEXIDADE_BASE),
            "Senioridade ENG1":         row.get(C_SENIORIDADE),
            "Data Fundação":            row.get(C_DATA_FUND),
            "Data Terraplenagem":       row.get(C_DATA_TERRA),
            "Data Encerramento Módulo": row.get(C_DATA_ENCERR),
            "Marco Início Obra A":      marco_valor,
            "Simultaneidade":           None,
            "Fonte da Próxima Obra":    None,
            "Origem Sequenciamento":    None,
            "Latência (Dias)":          None,
            "Distância (km)":           None,
            "Sobreposição":             None,
        })

        tem_prox = pd.notna(row.get(C_PROX_OBRA)) and str(row.get(C_PROX_OBRA, "")).strip() != ""
        if not tem_prox:
            continue

        id_prox   = row.get(C_ID_PROX)
        emp_match = mapa_emp.get(id_prox, {})

        linhas.append({
            "Linha":                    linha_id,
            "Tipo de Linha":            "Existente",
            "Ordem":                    2,
            "OBRA":                     row.get(C_PROX_OBRA),
            "Cód. CRM":                 id_prox,
            "Regional":                 emp_match.get(C_REGIONAL),
            "Cidade":                   row.get(C_CIDADE_PROX),
            "CLUSTER":                  emp_match.get(C_CLUSTER_EMP),
            "Complexidade Obra":        emp_match.get(C_COMPLEXIDADE_EMP),
            "Senioridade ENG1":         None,
            "Data Fundação":            emp_match.get(C_FUND_EMP),
            "Data Terraplenagem":       row.get(C_TERRA_PROX),
            "Data Encerramento Módulo": row.get(C_ENCERR_PROX),
            "Marco Início Obra A":      None,
            "Simultaneidade":           None,
            "Fonte da Próxima Obra":    row.get(C_FONTE_PROX),
            "Origem Sequenciamento":    row.get(C_ORIGEM),
            "Latência (Dias)":          row.get(C_LATENCIA),
            "Distância (km)":           row.get(C_DISTANCIA),
            "Sobreposição":             row.get("Sobreposição", "Não"),
        })

    for item in df_simultaneas:
        row             = item["_row"]
        marco_valor_sim = row.get(c_marco_base) if c_marco_base in row.index else None
        linhas.append({
            "Linha":                    item["_linha_id"],
            "Tipo de Linha":            "Existente",
            "Ordem":                    1,
            "OBRA":                     row.get(C_OBRA),
            "Cód. CRM":                 row.get(C_COD_CRM),
            "Regional":                 row.get(C_REGIONAL),
            "Cidade":                   row.get(C_CIDADE),
            "CLUSTER":                  row.get(C_CLUSTER),
            "Complexidade Obra":        row.get(C_COMPLEXIDADE_BASE),
            "Senioridade ENG1":         row.get(C_SENIORIDADE),
            "Data Fundação":            row.get(C_DATA_FUND),
            "Data Terraplenagem":       row.get(C_DATA_TERRA),
            "Data Encerramento Módulo": row.get(C_DATA_ENCERR),
            "Marco Início Obra A":      marco_valor_sim,
            "Simultaneidade":           "Sim — devolvida ao pool",
            "Fonte da Próxima Obra":    None,
            "Origem Sequenciamento":    None,
            "Latência (Dias)":          None,
            "Distância (km)":           None,
            "Sobreposição":             None,
        })

    for _, row in df_novas_linhas.iterrows():
        linhas.append({
            "Linha":                    row["Linha"],
            "Tipo de Linha":            "Nova",
            "Ordem":                    row["Ordem"],
            "OBRA":                     row["OBRA"],
            "Cód. CRM":                 row["Cód. CRM"],
            "Regional":                 row["Regional"],
            "Cidade":                   row["Cidade"],
            "CLUSTER":                  row["CLUSTER"],
            "Complexidade Obra":        row["Complexidade Obra"],
            "Senioridade ENG1":         None,
            "Data Fundação":            row["Data Fundação"],
            "Data Terraplenagem":       row["Data Terraplenagem"],
            "Data Encerramento Módulo": row["Data Encerramento Módulo"],
            "Marco Início Obra A":      None,
            "Simultaneidade":           None,
            "Fonte da Próxima Obra":    row["Fonte da Próxima Obra"],
            "Origem Sequenciamento":    row["Origem Sequenciamento"],
            "Latência (Dias)":          row["Latência (Dias)"],
            "Distância (km)":           row["Distância (km)"],
            "Sobreposição":             row.get("Sobreposição", "Não"),
        })

    return pd.DataFrame(linhas, columns=colunas_saida)
