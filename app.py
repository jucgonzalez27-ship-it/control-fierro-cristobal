import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import date

st.set_page_config(page_title="Control Fierro Terreno", layout="wide")

# =========================
# CONFIG
# =========================
DIAMETROS = ["Ø8", "Ø10", "Ø12", "Ø16", "Ø18", "Ø22"]
ELEMENTOS = ["Losa", "Muro", "Viga", "Pilar", "Fundación"]

PESO_POR_METRO = {
    "Ø8": 0.395,
    "Ø10": 0.617,
    "Ø12": 0.888,
    "Ø16": 1.58,
    "Ø18": 2.00,
    "Ø22": 2.98,
}

COLUMNAS_STOCK = [
    "Diametro",
    "Largo Barra (m)",
    "Cantidad Barras"
]

COLUMNAS_CONSUMO = [
    "Fecha",
    "Nivel",
    "Eje Numeral",
    "Eje Literal",
    "Elemento",
    "Diametro",
    "Largo Corte (m)",
    "Cantidad Piezas",
    "Largo Barra Usada (m)",
    "Barras Consumidas",
    "Metros Teoricos",
    "Despunte (m)",
    "Kg Estimados"
]

# =========================
# INICIALIZACIÓN
# =========================
def inicializar_datos():
    if "df_stock" not in st.session_state:
        st.session_state.df_stock = pd.DataFrame(columns=COLUMNAS_STOCK)

    if "df_consumo" not in st.session_state:
        st.session_state.df_consumo = pd.DataFrame(columns=COLUMNAS_CONSUMO)


# =========================
# LIMPIEZA Y UTILIDADES
# =========================
def limpiar_stock(df_stock):
    df = df_stock.copy()

    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_STOCK)

    for col in COLUMNAS_STOCK:
        if col not in df.columns:
            df[col] = None

    df["Diametro"] = df["Diametro"].astype(str).str.strip()
    df["Largo Barra (m)"] = pd.to_numeric(df["Largo Barra (m)"], errors="coerce").fillna(0)
    df["Cantidad Barras"] = pd.to_numeric(df["Cantidad Barras"], errors="coerce").fillna(0).astype(int)

    df = df[df["Diametro"] != ""].copy()
    return df


def limpiar_consumo(df_consumo):
    df = df_consumo.copy()

    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_CONSUMO)

    for col in COLUMNAS_CONSUMO:
        if col not in df.columns:
            df[col] = None

    numeric_cols = [
        "Largo Corte (m)",
        "Cantidad Piezas",
        "Largo Barra Usada (m)",
        "Barras Consumidas",
        "Metros Teoricos",
        "Despunte (m)",
        "Kg Estimados"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def obtener_opciones_largo_por_diametro(df_stock, diametro):
    df = limpiar_stock(df_stock)
    opciones = df[(df["Diametro"] == diametro) & (df["Cantidad Barras"] > 0)].copy()

    if opciones.empty:
        return []

    largos = sorted(opciones["Largo Barra (m)"].dropna().unique().tolist())
    return largos


def sugerir_largo_mas_conveniente(largos_disponibles, largo_corte):
    if not largos_disponibles:
        return None

    candidatos = [l for l in largos_disponibles if l >= largo_corte]
    if candidatos:
        return min(candidatos)

    return max(largos_disponibles)


def calcular_consumo(largo_corte, cantidad_piezas, largo_barra, diametro):
    metros_teoricos = largo_corte * cantidad_piezas

    if largo_barra <= 0 or largo_corte <= 0:
        return {
            "Metros Teoricos": 0,
            "Barras Consumidas": 0,
            "Despunte (m)": 0,
            "Kg Estimados": 0
        }

    piezas_por_barra = int(largo_barra // largo_corte)

    if piezas_por_barra <= 0:
        barras_consumidas = cantidad_piezas
    else:
        barras_consumidas = -(-cantidad_piezas // piezas_por_barra)  # ceil division

    despunte = (barras_consumidas * largo_barra) - metros_teoricos
    kg_estimados = metros_teoricos * PESO_POR_METRO.get(diametro, 0)

    return {
        "Metros Teoricos": round(metros_teoricos, 2),
        "Barras Consumidas": int(barras_consumidas),
        "Despunte (m)": round(despunte, 2),
        "Kg Estimados": round(kg_estimados, 2)
    }


def descontar_stock(df_stock, diametro, largo_barra_usada, barras_consumidas):
    df = limpiar_stock(df_stock)

    mask = (
        (df["Diametro"] == diametro) &
        (df["Largo Barra (m)"] == float(largo_barra_usada))
    )

    idxs = df[mask].index.tolist()

    if not idxs:
        return df, False, "No existe esa combinación de diámetro y largo en stock."

    idx = idxs[0]
    disponible = int(df.at[idx, "Cantidad Barras"])

    if disponible < barras_consumidas:
        return df, False, f"Stock insuficiente. Disponibles: {disponible} barras."

    df.at[idx, "Cantidad Barras"] = disponible - barras_consumidas
    return df, True, "Stock descontado correctamente."


def clasificar_semaforo_stock(df_stock):
    df = limpiar_stock(df_stock)

    if df.empty:
        return "🔴", "Sin stock cargado"

    total_barras = int(df["Cantidad Barras"].sum())

    if total_barras <= 0:
        return "🔴", "Falta stock"

    resumen = df.groupby("Diametro")["Cantidad Barras"].sum().reset_index()
    criticos = resumen[resumen["Cantidad Barras"] <= 2]

    if not criticos.empty:
        return "🟡", "Stock ajustado"

    return "🟢", "Stock controlado"


def resumen_diametros_criticos(df_stock):
    df = limpiar_stock(df_stock)

    if df.empty:
        return pd.DataFrame(columns=["Diametro", "Cantidad Barras"])

    resumen = (
        df.groupby("Diametro", dropna=False)["Cantidad Barras"]
        .sum()
        .reset_index()
        .sort_values(by="Cantidad Barras", ascending=True)
    )
    return resumen


def generar_excel(df_stock, df_consumo):
    output = BytesIO()

    df_stock_limpio = limpiar_stock(df_stock)
    df_consumo_limpio = limpiar_consumo(df_consumo)

    resumen_stock = (
        df_stock_limpio.groupby(["Diametro", "Largo Barra (m)"], dropna=False)["Cantidad Barras"]
        .sum()
        .reset_index()
        .sort_values(by=["Diametro", "Largo Barra (m)"])
        if not df_stock_limpio.empty else pd.DataFrame(columns=["Diametro", "Largo Barra (m)", "Cantidad Barras"])
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_stock_limpio.to_excel(writer, index=False, sheet_name="Stock")
        df_consumo_limpio.to_excel(writer, index=False, sheet_name="Consumos")
        resumen_stock.to_excel(writer, index=False, sheet_name="Resumen Stock")

    output.seek(0)
    return output


# =========================
# CUBICACIÓN EXCEL
# =========================
def preparar_cubicacion_alex(df):
    df = df.copy()

    cols_necesarias = [
        "Estructura", "Eje", "Elemento", "Tipo", "Detalle",
        "f (mm)", "Cant.", "L Unit (m)", "Peso (kg)",
        "A", "B", "C", "D", "E", "F", "G"
    ]

    for c in cols_necesarias:
        if c not in df.columns:
            df[c] = np.nan

    df["Cant."] = pd.to_numeric(df["Cant."], errors="coerce").fillna(0)
    df["L Unit (m)"] = pd.to_numeric(df["L Unit (m)"], errors="coerce").fillna(0)
    df["Peso (kg)"] = pd.to_numeric(df["Peso (kg)"], errors="coerce").fillna(0)
    df["f (mm)"] = pd.to_numeric(df["f (mm)"], errors="coerce").fillna(0)

    # normalización texto
    for c in ["Estructura", "Eje", "Elemento", "Tipo", "Detalle"]:
        df[c] = df[c].astype(str).str.strip()

    # Firma geométrica individual
    cols_dim = ["A", "B", "C", "D", "E", "F", "G"]
    df["FirmaBarra"] = (
        df["Detalle"].astype(str).str.strip() + "|" +
        df["f (mm)"].astype(str) + "|" +
        df["L Unit (m)"].astype(str) + "|" +
        df[cols_dim].astype(str).agg("|".join, axis=1)
    )

    return df


def distancia_jaccard(set1, set2):
    if not set1 and not set2:
        return 0
    inter = len(set1.intersection(set2))
    union = len(set1.union(set2))
    if union == 0:
        return 0
    return 1 - inter / union


def detectar_grupos(df_filtrado, ventana=4, umbral=0.35):
    """
    Heurística inicial:
    - recorre en orden
    - mira la mezcla de firmas recientes
    - si cambia bastante, crea un grupo nuevo
    """
    df = df_filtrado.copy().reset_index(drop=True)

    if df.empty:
        df["Grupo"] = []
        return df

    firmas = df["FirmaBarra"].tolist()
    grupo_ids = []
    grupo_actual = 1
    ventana_firmas = []

    for i, firma in enumerate(firmas):
        if i == 0:
            grupo_ids.append(grupo_actual)
            ventana_firmas = [firma]
            continue

        prev_set = set(ventana_firmas[-ventana:])
        curr_set = set(ventana_firmas[-ventana:] + [firma])
        d = distancia_jaccard(prev_set, curr_set)

        if d > umbral:
            grupo_actual += 1
            ventana_firmas = [firma]
        else:
            ventana_firmas.append(firma)

        grupo_ids.append(grupo_actual)

    df["Grupo"] = grupo_ids
    return df


def resumir_partida_por_grupo(df_filtrado):
    if df_filtrado.empty:
        return pd.DataFrame()

    resumen = (
        df_filtrado
        .groupby(["Grupo", "f (mm)", "L Unit (m)", "Detalle"], dropna=False)
        .agg(
            Cantidad=("Cant.", "sum"),
            Peso_Total=("Peso (kg)", "sum")
        )
        .reset_index()
        .sort_values(by=["Grupo", "f (mm)", "L Unit (m)", "Detalle"])
    )
    return resumen


# =========================
# APP
# =========================
inicializar_datos()

st.title("🔩 Control Fierro Terreno")
st.caption("Consumo real + stock + consulta de cubicación")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Inicio",
    "Consumo",
    "Stock",
    "Reporte",
    "Cubicación"
])

# =========================
# TAB 1 - INICIO
# =========================
with tab1:
    st.subheader("Panel principal")

    df_stock = limpiar_stock(st.session_state.df_stock)
    df_consumo = limpiar_consumo(st.session_state.df_consumo)

    hoy = str(date.today())
    consumo_hoy = df_consumo[df_consumo["Fecha"].astype(str) == hoy] if not df_consumo.empty else pd.DataFrame()

    kg_hoy = round(consumo_hoy["Kg Estimados"].sum(), 2) if not consumo_hoy.empty else 0
    barras_hoy = int(consumo_hoy["Barras Consumidas"].sum()) if not consumo_hoy.empty else 0
    metros_hoy = round(consumo_hoy["Metros Teoricos"].sum(), 2) if not consumo_hoy.empty else 0
    registros_hoy = len(consumo_hoy)

    emoji, texto = clasificar_semaforo_stock(df_stock)

    if emoji == "🟢":
        st.success(f"{emoji} SEMÁFORO GENERAL: {texto}")
    elif emoji == "🟡":
        st.warning(f"{emoji} SEMÁFORO GENERAL: {texto}")
    else:
        st.error(f"{emoji} SEMÁFORO GENERAL: {texto}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Consumo del día (kg)", kg_hoy)
    c2.metric("Barras consumidas hoy", barras_hoy)
    c3.metric("Metros del día", metros_hoy)
    c4.metric("Registros de hoy", registros_hoy)

    st.markdown("### Diámetros críticos")
    df_crit = resumen_diametros_criticos(df_stock)
    if not df_crit.empty:
        st.dataframe(df_crit, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay stock cargado.")

    st.markdown("### Últimos registros")
    if not df_consumo.empty:
        ultimos = df_consumo.sort_index(ascending=False).head(10)
        st.dataframe(ultimos, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay consumos registrados.")

# =========================
# TAB 2 - REGISTRAR CONSUMO
# =========================
with tab2:
    st.subheader("Registrar consumo")

    col1, col2 = st.columns(2)

    with col1:
        fecha_reg = st.date_input("Fecha", value=date.today())
        nivel = st.text_input("Nivel")
        eje_numeral = st.text_input("Eje numeral")
        eje_literal = st.text_input("Eje literal")

    with col2:
        elemento = st.selectbox("Elemento", ELEMENTOS)
        diametro = st.selectbox("Diámetro", DIAMETROS)
        largo_corte = st.number_input("Largo de corte (m)", min_value=0.01, step=0.01, format="%.2f")
        cantidad_piezas = st.number_input("Cantidad de piezas", min_value=1, step=1)

    opciones_largo = obtener_opciones_largo_por_diametro(st.session_state.df_stock, diametro)

    st.markdown("### Selección de barra desde stock")

    if not opciones_largo:
        st.error("No hay stock disponible para ese diámetro. Carga stock antes de registrar consumo.")
        largo_barra_usada = 0.0
    else:
        sugerido = sugerir_largo_mas_conveniente(opciones_largo, largo_corte)

        if len(opciones_largo) == 1:
            largo_barra_usada = opciones_largo[0]
            st.info(f"Largo automático desde stock: {largo_barra_usada} m")
        else:
            st.info(f"Sugerencia automática: {sugerido} m")
            largo_barra_usada = st.selectbox(
                "Elige largo de barra a usar",
                options=opciones_largo,
                index=opciones_largo.index(sugerido) if sugerido in opciones_largo else 0
            )

    if largo_barra_usada > 0:
        resultados = calcular_consumo(
            largo_corte=largo_corte,
            cantidad_piezas=int(cantidad_piezas),
            largo_barra=float(largo_barra_usada),
            diametro=diametro
        )
    else:
        resultados = {
            "Metros Teoricos": 0,
            "Barras Consumidas": 0,
            "Despunte (m)": 0,
            "Kg Estimados": 0
        }

    st.markdown("### Resultado automático")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Metros teóricos", resultados["Metros Teoricos"])
    r2.metric("Barras consumidas", resultados["Barras Consumidas"])
    r3.metric("Despunte (m)", resultados["Despunte (m)"])
    r4.metric("Kg estimados", resultados["Kg Estimados"])

    if st.button("➕ Guardar consumo", use_container_width=True):
        if not nivel.strip():
            st.error("Debes indicar el nivel.")
        elif not eje_numeral.strip() and not eje_literal.strip():
            st.error("Debes indicar al menos un eje.")
        elif largo_barra_usada <= 0:
            st.error("No se puede guardar sin stock disponible.")
        elif largo_corte > largo_barra_usada:
            st.error("El largo de corte no puede ser mayor al largo de barra usado.")
        else:
            df_stock_actualizado, ok, mensaje = descontar_stock(
                st.session_state.df_stock,
                diametro,
                largo_barra_usada,
                resultados["Barras Consumidas"]
            )

            if not ok:
                st.error(mensaje)
            else:
                nuevo = pd.DataFrame([{
                    "Fecha": str(fecha_reg),
                    "Nivel": nivel,
                    "Eje Numeral": eje_numeral,
                    "Eje Literal": eje_literal,
                    "Elemento": elemento,
                    "Diametro": diametro,
                    "Largo Corte (m)": largo_corte,
                    "Cantidad Piezas": int(cantidad_piezas),
                    "Largo Barra Usada (m)": float(largo_barra_usada),
                    "Barras Consumidas": resultados["Barras Consumidas"],
                    "Metros Teoricos": resultados["Metros Teoricos"],
                    "Despunte (m)": resultados["Despunte (m)"],
                    "Kg Estimados": resultados["Kg Estimados"],
                }])

                st.session_state.df_stock = df_stock_actualizado
                st.session_state.df_consumo = pd.concat(
                    [st.session_state.df_consumo, nuevo],
                    ignore_index=True
                )

                st.success("Consumo guardado y stock descontado correctamente.")
                st.rerun()

# =========================
# TAB 3 - STOCK
# =========================
with tab3:
    st.subheader("Stock disponible")

    if st.session_state.df_stock.empty:
        st.warning("Aún no has cargado stock. Agrega el stock real según diámetro, largo y cantidad.")

    st.info("Aquí defines el stock real por diámetro y largo de barra.")

    df_stock_editado = st.data_editor(
        limpiar_stock(st.session_state.df_stock),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )

    col_guardar, col_limpiar = st.columns(2)

    with col_guardar:
        if st.button("💾 Guardar stock", use_container_width=True):
            st.session_state.df_stock = limpiar_stock(df_stock_editado)
            st.success("Stock guardado correctamente.")
            st.rerun()

    with col_limpiar:
        if st.button("🗑️ Reiniciar stock", use_container_width=True):
            st.session_state.df_stock = pd.DataFrame(columns=COLUMNAS_STOCK)
            st.success("Stock reiniciado.")
            st.rerun()

    st.markdown("### Agregar línea rápida de stock")

    s1, s2, s3 = st.columns(3)
    with s1:
        nuevo_diam = st.selectbox("Diámetro", DIAMETROS, key="nuevo_diam")
    with s2:
        nuevo_largo = st.number_input("Largo barra (m)", min_value=0.1, step=0.1, value=12.0, key="nuevo_largo")
    with s3:
        nueva_cant = st.number_input("Cantidad barras", min_value=1, step=1, value=1, key="nueva_cant")

    if st.button("➕ Agregar stock rápido"):
        nueva_fila = pd.DataFrame([{
            "Diametro": nuevo_diam,
            "Largo Barra (m)": float(nuevo_largo),
            "Cantidad Barras": int(nueva_cant)
        }])

        st.session_state.df_stock = pd.concat(
            [limpiar_stock(st.session_state.df_stock), nueva_fila],
            ignore_index=True
        )
        st.success("Stock agregado.")
        st.rerun()

# =========================
# TAB 4 - REPORTE
# =========================
with tab4:
    st.subheader("Reporte general")

    df_stock = limpiar_stock(st.session_state.df_stock)
    df_consumo = limpiar_consumo(st.session_state.df_consumo)

    resumen_stock = (
        df_stock.groupby(["Diametro", "Largo Barra (m)"], dropna=False)["Cantidad Barras"]
        .sum()
        .reset_index()
        .sort_values(by=["Diametro", "Largo Barra (m)"])
        if not df_stock.empty else pd.DataFrame(columns=["Diametro", "Largo Barra (m)", "Cantidad Barras"])
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total registros", len(df_consumo))
    c2.metric("Total barras consumidas", int(df_consumo["Barras Consumidas"].sum()) if not df_consumo.empty else 0)
    c3.metric("Total despunte (m)", round(df_consumo["Despunte (m)"].sum(), 2) if not df_consumo.empty else 0)
    c4.metric("Total kg estimados", round(df_consumo["Kg Estimados"].sum(), 2) if not df_consumo.empty else 0)

    st.markdown("### Consumos registrados")
    if not df_consumo.empty:
        st.dataframe(df_consumo.sort_index(ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay consumos registrados.")

    st.markdown("### Stock restante")
    if not resumen_stock.empty:
        st.dataframe(resumen_stock, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay stock cargado.")

    excel_file = generar_excel(df_stock, df_consumo)

    st.download_button(
        label="📥 Descargar Excel",
        data=excel_file,
        file_name="control_fierro_terreno.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# =========================
# TAB 5 - CUBICACION
# =========================
with tab5:
    st.subheader("Cubicacion")

    archivo_alex = st.file_uploader("Subir cubicación de Alex", type=["xlsx"], key="archivo_alex")

    if archivo_alex is not None:
        try:
            df_raw = pd.read_excel(archivo_alex)
            df_alex = preparar_cubicacion_alex(df_raw)

            col1, col2 = st.columns(2)
            with col1:
                estructura_sel = st.selectbox(
                    "Estructura",
                    sorted(df_alex["Estructura"].dropna().unique().tolist())
                )
                eje_sel = st.selectbox(
                    "Eje",
                    sorted(df_alex["Eje"].dropna().unique().tolist())
                )

            with col2:
                elemento_sel = st.selectbox(
                    "Elemento",
                    sorted(df_alex["Elemento"].dropna().unique().tolist())
                )
                tipo_sel = st.selectbox(
                    "Tipo",
                    sorted(df_alex["Tipo"].dropna().unique().tolist())
                )

            col3, col4 = st.columns(2)
            with col3:
                ventana = st.slider("Ventana de detección", min_value=2, max_value=8, value=4, step=1)
            with col4:
                umbral = st.slider("Sensibilidad de agrupación", min_value=0.10, max_value=0.90, value=0.35, step=0.05)

            df_filtrado = df_alex[
                (df_alex["Estructura"] == estructura_sel) &
                (df_alex["Eje"] == eje_sel) &
                (df_alex["Elemento"] == elemento_sel) &
                (df_alex["Tipo"] == tipo_sel)
            ].copy()

            st.markdown("### Filtrado")
            st.write(f"Filas encontradas: {len(df_filtrado)}")

            if not df_filtrado.empty:
                df_grupos = detectar_grupos(df_filtrado, ventana=ventana, umbral=umbral)
                df_resumen = resumir_partida_por_grupo(df_grupos)

                grupos_detectados = sorted(df_grupos["Grupo"].unique().tolist())

                c1, c2 = st.columns(2)
                c1.metric("Grupos detectados", len(grupos_detectados))
                c2.metric("Filas filtradas", len(df_grupos))

                grupo_sel = st.selectbox("Selecciona grupo detectado", grupos_detectados)

                st.markdown("### Resumen del grupo")
                resumen_grupo = df_resumen[df_resumen["Grupo"] == grupo_sel].copy()
                st.dataframe(resumen_grupo, use_container_width=True, hide_index=True)

                st.markdown("### Detalle del grupo")
                detalle_grupo = df_grupos[df_grupos["Grupo"] == grupo_sel].copy()
                st.dataframe(detalle_grupo, use_container_width=True, hide_index=True)

                st.markdown("### Vista completa con grupos")
                st.dataframe(df_grupos, use_container_width=True, hide_index=True)
            else:
                st.warning("No hay filas para esa combinación de estructura, eje, elemento y tipo.")

        except Exception as e:
            st.error(f"Error al leer o procesar el archivo: {e}")

st.markdown("---")
st.caption("Versión integrada: consumo real, stock y consulta estratégica de cubicación.")
