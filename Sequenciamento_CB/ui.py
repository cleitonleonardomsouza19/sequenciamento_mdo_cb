# ui.py

import io

import pandas as pd
import streamlit as st

from config import COLUNAS_ESPERADAS, COLUNAS_GERADAS, LEGENDA


def render_guia_colunas():
    with st.expander("📋 Ver estrutura esperada das planilhas (clique para expandir)", expanded=False):
        st.markdown("### 📌 Legenda de Obrigatoriedade")
        cols_leg = st.columns(2)
        for idx, (icone, desc) in enumerate(LEGENDA.items()):
            cols_leg[idx].info(f"**{icone}**\n\n{desc}")
        st.divider()
        icones_aba = {"Base": "📄 Planilha 1 — Base", "Sheet1": "📄 Planilha 2 — Todos Empreendimentos"}
        for aba, info in COLUNAS_ESPERADAS.items():
            st.markdown(f"### 🗂️ {icones_aba[aba]} › Guia: `{aba}`")
            st.caption(info["descricao"])
            df_cols         = pd.DataFrame(info["colunas"])
            df_cols.columns = ["Coluna", "Tipo de Dado", "Obrigatório", "Descrição"]
            def colorir_linha(row):
                if row["Obrigatório"] == "✅":
                    return ["background-color: #e6f4ea"] * len(row)
                return ["background-color: #f1f3f4"] * len(row)
            st.dataframe(
                df_cols.style.apply(colorir_linha, axis=1),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Coluna":       st.column_config.TextColumn("Coluna",       width="medium"),
                    "Tipo de Dado": st.column_config.TextColumn("Tipo de Dado", width="small"),
                    "Obrigatório":  st.column_config.TextColumn("Obrigatório",  width="small"),
                    "Descrição":    st.column_config.TextColumn("Descrição",    width="large"),
                }
            )
            st.markdown("")
        st.divider()
        st.markdown("### ⚙️ Colunas geradas automaticamente pelo sequenciador")
        st.caption("Adicionadas na planilha de saída — não precisam existir nas planilhas originais.")
        df_geradas         = pd.DataFrame(COLUNAS_GERADAS)
        df_geradas.columns = ["Coluna", "Tipo de Dado", "Descrição"]
        st.dataframe(
            df_geradas.style.apply(lambda row: ["background-color: #fff8e1"] * len(row), axis=1),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Coluna":       st.column_config.TextColumn("Coluna",       width="medium"),
                "Tipo de Dado": st.column_config.TextColumn("Tipo de Dado", width="small"),
                "Descrição":    st.column_config.TextColumn("Descrição",    width="large"),
            }
        )
        st.markdown(
            "💡 **Regra de complexidade:** JUNIOR → apenas NÃO COMPLEXO | "
            "PLENO → NÃO COMPLEXO e MÉDIO | SENIOR → qualquer complexidade. "
            "**Simultaneidade:** quando uma linha possui N obras ao mesmo tempo, apenas a de maior encerramento "
            "é mantida ativa para sequenciamento; as demais são devolvidas ao pool de novas linhas."
        )


def render_upload():
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.markdown("#### 📄 Planilha 1 — Base")
        st.caption("Deve conter a guia **Base** com os engenheiros e obras atuais.")
        arquivo_base = st.file_uploader("Suba a planilha Base aqui", type=["xlsx"], key="upload_base")
    with col_up2:
        st.markdown("#### 📄 Planilha 2 — Todos Empreendimentos")
        st.caption("Deve conter a guia **Sheet1** com o catálogo de obras candidatas.")
        arquivo_empreendimentos = st.file_uploader("Suba a planilha de Empreendimentos aqui", type=["xlsx"], key="upload_emp")

    if arquivo_base and not arquivo_empreendimentos:
        st.info("⏳ Aguardando o upload da **Planilha 2 — Todos Empreendimentos** para continuar.")
    if arquivo_empreendimentos and not arquivo_base:
        st.info("⏳ Aguardando o upload da **Planilha 1 — Base** para continuar.")

    return arquivo_base, arquivo_empreendimentos


def render_preview(df_base, df_emp):
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.success(f"✅ Base carregada — {len(df_base)} registros")
        with st.expander("🔍 Pré-visualização — Base", expanded=False):
            st.dataframe(df_base, use_container_width=True)
    with col_info2:
        st.success(f"✅ Empreendimentos carregados — {len(df_emp)} registros")
        with st.expander("🔍 Pré-visualização — Sheet1", expanded=False):
            st.dataframe(df_emp, use_container_width=True)


def render_configuracao_marco() -> str:
    st.markdown("#### ⚙️ Configuração do Marco de Início da Obra B")
    st.caption(
        "Selecione qual data será usada como **marco de início** da Obra A (linhas existentes, Ordem 1). "
        "Essa data será exibida na coluna **'Marco Início Obra A'** no resultado."
    )
    marco = st.radio(
        label="Marco de início da Obra B:",
        options=["Terraplenagem", "Fundação"],
        index=1,
        horizontal=True,
        help=(
            "**Terraplenagem** → usa a coluna 'Data Terraplenagem' da guia Base.\n\n"
            "**Fundação** → usa a coluna 'Data Fundação' da guia Base."
        ),
        key="marco_inicio_obra_a"
    )
    if marco == "Terraplenagem":
        st.info("📌 Marco selecionado: **Terraplenagem** — coluna `Data Terraplenagem` (guia Base)")
    else:
        st.info("📌 Marco selecionado: **Fundação** — coluna `Data Fundação` (guia Base)")
    return marco


def render_filtro_latencia() -> tuple[int, int]:
    st.markdown("#### ⏱️ Tempo máximo de prateleira (latência) e sobreposição")
    st.caption(
        "**Latência** define o gap máximo (em meses) entre o **término da Obra A** e o **início da Obra B**. "
        "**Sobreposição** define quantos meses a Obra B pode começar **antes** do término da Obra A."
    )

    col_lat, col_sob = st.columns(2)

    with col_lat:
        st.markdown("**Latência máxima permitida:**")
        meses = st.selectbox(
            label="Latência máxima permitida:",
            options=[3, 4, 5, 6, 7],
            index=0,
            format_func=lambda x: f"{x} mês" if x == 1 else f"{x} meses",
            key="filtro_latencia",
            label_visibility="collapsed",
        )
        st.info(f"📌 Latência máxima: **{meses} meses** ({meses * 30} dias)")

    with col_sob:
        st.markdown("**Sobreposição máxima permitida:**")
        sobreposicao = st.selectbox(
            label="Sobreposição máxima permitida:",
            options=[0, 1, 2, 3],
            index=0,
            format_func=lambda x: "Sem sobreposição" if x == 0 else (f"{x} mês" if x == 1 else f"{x} meses"),
            key="filtro_sobreposicao",
            label_visibility="collapsed",
        )
        if sobreposicao == 0:
            st.info("📌 Sobreposição: **não permitida** — B só começa após A terminar")
        else:
            st.warning(f"📌 Sobreposição: **até {sobreposicao} meses** — B pode começar {sobreposicao * 30} dias antes de A terminar")

    return meses, sobreposicao


def render_filtro_senioridade() -> bool:
    st.markdown("#### 🎓 Filtro de Senioridade e Complexidade")
    st.caption(
        "Quando ativado, o sequenciador respeita a regra de complexidade por senioridade: "
        "JUNIOR → apenas NÃO COMPLEXO | PLENO → NÃO COMPLEXO e MÉDIO | SENIOR → qualquer complexidade. "
        "Quando desativado, esse critério é ignorado e apenas distância, cluster e latência são considerados."
    )
    usar = st.checkbox(
        label="Considerar senioridade e complexidade no sequenciamento",
        value=True,
        key="filtro_senioridade",
        help=(
            "✅ **Marcado** → aplica o filtro de complexidade conforme a senioridade do ENG1.\n\n"
            "☐ **Desmarcado** → ignora complexidade; sequencia usando apenas cluster, "
            "distância (≤ 200 km) e latência."
        ),
    )
    if usar:
        st.info("📌 Senioridade/complexidade: **ativada** — regras de complexidade serão aplicadas.")
    else:
        st.warning("📌 Senioridade/complexidade: **desativada** — obras serão sequenciadas sem restrição de complexidade.")
    return usar


def render_filtro_distancia_cluster() -> tuple[int, bool]:
    st.markdown("#### 📍 Distância máxima e cluster")
    st.caption(
        "Define o raio máximo (em km) entre a obra atual e a próxima obra candidata, "
        "e se o sequenciador pode sugerir obras de **cluster diferente** como fallback "
        "quando não houver candidatas no mesmo cluster."
    )

    col_dist, col_cluster = st.columns(2)

    with col_dist:
        distancia_km = st.number_input(
            label="Distância máxima entre obras (km):",
            min_value=25,
            max_value=1000,
            value=50,
            step=25,
            key="filtro_distancia_km",
            help="Obras em cidades com distância superior a esse valor serão ignoradas no sequenciamento.",
        )
        st.info(f"📌 Distância máxima: **{distancia_km} km**")

    with col_cluster:
        permitir_cluster_diferente = st.checkbox(
            label="Permitir obras de cluster diferente",
            value=True,
            key="filtro_cluster_diferente",
            help=(
                "✅ **Marcado** → se não houver candidatas no mesmo cluster, "
                "o sequenciador tenta obras de outros clusters (dentro do raio e latência).\n\n"
                "☐ **Desmarcado** → apenas obras do mesmo cluster são consideradas."
            ),
        )
        if permitir_cluster_diferente:
            st.info("📌 Cluster diferente: **permitido** — usado como fallback quando necessário.")
        else:
            st.warning("📌 Cluster diferente: **bloqueado** — apenas obras do mesmo cluster serão sugeridas.")

    return distancia_km, permitir_cluster_diferente


def render_botao_iniciar() -> bool:
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        clicou = st.button(
            label="▶️ Iniciar Sequenciamento",
            type="primary",
            key="btn_iniciar"
        )

    if clicou:
        st.session_state["sequenciamento_rodando"]    = True
        st.session_state["snap_usar_senioridade"]     = st.session_state.get("filtro_senioridade",       True)
        st.session_state["snap_distancia_km"]         = st.session_state.get("filtro_distancia_km",      50)
        st.session_state["snap_permitir_cluster"]     = st.session_state.get("filtro_cluster_diferente", True)
        st.session_state["snap_marco"]                = st.session_state.get("marco_inicio_obra_a",      "Fundação")
        st.session_state["snap_latencia"]             = st.session_state.get("filtro_latencia",          3)
        st.session_state["snap_sobreposicao"]         = st.session_state.get("filtro_sobreposicao",      0)

        # Inicializa o contador de cenário apenas na primeira execução da sessão
        if "contador_cenario" not in st.session_state:
            st.session_state["contador_cenario"] = 1

    if not st.session_state.get("sequenciamento_rodando", False):
        with col_status:
            st.info("⏳ Configure os parâmetros acima e clique em **▶️ Iniciar Sequenciamento** para começar.")
        return False

    return True


def render_resumo_parametros():
    marco            = st.session_state.get("snap_marco",            "Fundação")
    latencia         = st.session_state.get("snap_latencia",         3)
    sobreposicao     = st.session_state.get("snap_sobreposicao",     0)
    usar_senioridade = st.session_state.get("snap_usar_senioridade", True)
    distancia_km     = st.session_state.get("snap_distancia_km",     50)
    permitir_cluster = st.session_state.get("snap_permitir_cluster", True)

    with st.expander("🧾 Parâmetros utilizados neste sequenciamento (clique para expandir)", expanded=True):
        st.caption(
            "Estes foram os valores **ativos no momento em que ▶️ Iniciar Sequenciamento foi clicado**. "
            "A planilha gerada reflete exatamente estes critérios."
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**⚙️ Marco de Início da Obra A**")
            st.info(f"📌 {marco}")

            st.markdown("**⏱️ Latência Máxima**")
            st.info(f"📌 {latencia} meses ({latencia * 30} dias)")

            st.markdown("**🔀 Sobreposição Máxima**")
            if sobreposicao == 0:
                st.info("📌 Sem sobreposição permitida")
            else:
                st.warning(f"📌 Até {sobreposicao} meses ({sobreposicao * 30} dias)")

        with col2:
            st.markdown("**🎓 Senioridade e Complexidade**")
            if usar_senioridade:
                st.success("✅ Ativada — regras de complexidade por senioridade aplicadas")
            else:
                st.warning("⚠️ Desativada — complexidade ignorada no sequenciamento")

            st.markdown("**📍 Distância Máxima entre Obras**")
            st.info(f"📌 {distancia_km} km")

        with col3:
            st.markdown("**🗂️ Cluster Diferente como Fallback**")
            if permitir_cluster:
                st.success("✅ Permitido — usado quando não há candidatas no mesmo cluster")
            else:
                st.warning("⚠️ Bloqueado — apenas obras do mesmo cluster consideradas")


def render_diagnostico(df_base):
    from utils import sigla_senioridade, nivel_senioridade, complexidades_permitidas_para
    with st.expander("🔬 Diagnóstico: valores únicos de Senioridade ENG1", expanded=False):
        if "Senioridade ENG1" in df_base.columns:
            vals = df_base["Senioridade ENG1"].dropna().unique().tolist()
            st.write("Valores encontrados na coluna:", vals)
            for v in vals:
                st.write(
                    f"  `{v}` → sigla: **'{sigla_senioridade(v)}'** | "
                    f"nível: **'{nivel_senioridade(v)}'** | "
                    f"complexidades permitidas: **{complexidades_permitidas_para(v)}**"
                )
        else:
            st.warning("Coluna 'Senioridade ENG1' não encontrada na Base.")


def render_resultado(df_output):
    with st.expander("📊 Ver resultado — Output Empilhado por Linha", expanded=True):
        st.caption(
            "🔑 **Linha** é o pivot. "
            "**Tipo de Linha**: `Existente` = veio da guia Base | `Nova` = criada pelo app. "
            "**Marco Início Obra A**: data usada como início da Obra A conforme seleção do usuário. "
            "**Simultaneidade**: `Sim — devolvida ao pool` = obra estava simultânea e foi redistribuída. "
            "**Fonte da Próxima Obra**: `DH` = veio da guia Base | `Ferramenta` = sugerida pelo app. "
            "**Origem Sequenciamento**: `Sequenciamento DH` = já existia na Base | `Sequenciamento - ferramenta` = app sequenciou."
        )
        st.dataframe(
            df_output.sort_values(["Linha", "Ordem"], na_position="last"),
            use_container_width=True,
            hide_index=True,
        )


# ─────────────────────────────────────────────────────────────
# Funções auxiliares para o download com nome dinâmico
# ─────────────────────────────────────────────────────────────

def _montar_nome_arquivo() -> str:
    """
    Monta o nome do arquivo no padrão:
    NN-SEQ-CB-MARCO-LAT-SOBR-SENC-DIST-CLUS.xlsx
    Lê os parâmetros travados no session_state pelo botão iniciar.
    """
    marco            = st.session_state.get("snap_marco",            "Fundação")
    latencia         = st.session_state.get("snap_latencia",         3)
    sobreposicao     = st.session_state.get("snap_sobreposicao",     0)
    usar_senioridade = st.session_state.get("snap_usar_senioridade", True)
    distancia_km     = st.session_state.get("snap_distancia_km",     50)
    permitir_cluster = st.session_state.get("snap_permitir_cluster", True)

    nn       = str(st.session_state.get("contador_cenario", 1)).zfill(2)
    marco_cod = "FND" if marco == "Fundação" else "TRP"
    lat_cod   = f"L{latencia}"
    sob_cod   = f"S{sobreposicao}"
    senc_cod  = "SC1" if usar_senioridade else "SC0"
    dist_cod  = f"D{int(distancia_km)}"
    clus_cod  = "CL0" if permitir_cluster else "CL1"

    return f"{nn}-SEQ-CB-{marco_cod}-{lat_cod}-{sob_cod}-{senc_cod}-{dist_cod}-{clus_cod}.xlsx"


def _incrementar_contador():
    """Incrementa o NN a cada clique no botão de download."""
    st.session_state["contador_cenario"] = st.session_state.get("contador_cenario", 1) + 1


def render_download(df_output, df_emp):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_output.sort_values(["Linha", "Ordem"], na_position="last").to_excel(
            writer, sheet_name="Sequenciamento", index=False
        )
        df_emp.to_excel(writer, sheet_name="Todos Empreendimentos", index=False)

    nome_arquivo = _montar_nome_arquivo()

    st.download_button(
        label     = "📥 Baixar Planilha Sequenciada",
        data      = buffer.getvalue(),
        file_name = nome_arquivo,
        mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click  = _incrementar_contador,
    )

    st.caption(f"📄 Nome do arquivo que será baixado: `{nome_arquivo}`")
