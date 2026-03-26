import streamlit as st
import pandas as pd
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
# FUNCIONES BASE
# =========================
def inicializar_datos():
   if "df_stock" not in st.session_state:
    st.session_state.df_stock = pd.DataFrame(columns=COLUMNAS_STOCK)

    if "df_consumo" not in st.session_state:
        st.session_state.df_consumo = pd.DataFrame(columns=COLUMNAS_CONSUMO)


def limpiar_stock(df_stock):
    df = df_stock.copy()
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_STOCK)

    df["Largo Barra (m)"] = pd.to_numeric(df["Largo Barra (m)"], errors="coerce").fillna(0)
    df["Cantidad Barras"] = pd.to_numeric(df["Cantidad Barras"], errors="coerce").fillna(0).astype(int)
    return df


def limpiar_consumo(df_consumo):
    df = df_consumo.copy()
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_CONSUMO)

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

    if largo_barra <= 0:
        barras_consumidas = 0
        despunte = 0
    else:
        piezas_por_barra = int(largo_barra // largo_corte) if largo_corte > 0 else 0

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
        "Kg Estimados": round(kg_estimados, 2),
    }


def descontar_stock(df_stock, diametro, largo_barra_usada, barras_consumidas):
    df = limpiar_stock(df_stock)

    mask = (
        (df["Diametro"] == diametro) &
        (df["Largo Barra (m)"] == float(largo_barra_usada))
    )

    indices = df[mask].index.tolist()

    if not indices:
        return df, False, "No se encontró esa combinación diámetro/largo en stock."

    idx = indices[0]
    disponible = int(df.at[idx, "Cantidad Barras"])

    if disponible < barras_consumidas:
        return df, False, f"Stock insuficiente. Disponibles: {disponible} barras."

    df.at[idx, "Cantidad Barras"] = disponible - barras_consumidas
    return df, True, "Stock descontado correctamente."


def clasificar_semaforo_stock(df_stock, df_consumo):
    df_s = limpiar_stock(df_stock)
    df_c = limpiar_consumo(df_consumo)

    stock_total_barras = df_s["Cantidad Barras"].sum() if not df_s.empty else 0

    if stock_total_barras <= 0:
        return "🔴", "Falta stock"

    if df_s.empty:
        return "🔴", "Sin stock"

    stock_por_diam = df_s.groupby("Diametro")["Cantidad Barras"].sum().reset_index()
    criticos = stock_por_diam[stock_por_diam["Cantidad Barras"] <= 2]

    if not criticos.empty:
        return "🟡", "Stock ajustado"

    return "🟢", "Stock controlado"


def resumen_diametros_criticos(df_stock):
    df_s = limpiar_stock(df_stock)
    if df_s.empty:
        return pd.DataFrame(columns=["Diametro", "Cantidad Barras"])

    resumen = df_s.groupby("Diametro")["Cantidad Barras"].sum().reset_index()
    resumen = resumen.sort_values(by="Cantidad Barras", ascending=True)
    return resumen


def generar_excel(df_stock, df_consumo, df_resumen_stock):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        limpiar_stock(df_stock).to_excel(writer, index=False, sheet_name="Stock")
        limpiar_consumo(df_consumo).to_excel(writer, index=False, sheet_name="Consumos")
        df_resumen_stock.to_excel(writer, index=False, sheet_name="Resumen Stock")
    output.seek(0)
    return output


# =========================
# APP
# =========================
inicializar_datos()

st.title("🔩 Control Fierro Terreno")
st.caption("Registro de consumo real + stock + semáforos")

tab1, tab2, tab3, tab4 = st.tabs([
    "Inicio",
    "Registrar Consumo",
    "Stock",
    "Reporte"
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
    barras_hoy = int(consumo_hoy["Barras Consumidas"].sum()) if not consumo_hoy.empty else 0
    kg_hoy = round(consumo_hoy["Kg Estimados"].sum(), 2) if not consumo_hoy.empty else 0
    metros_hoy = round(consumo_hoy["Metros Teoricos"].sum(), 2) if not consumo_hoy.empty else 0

    emoji, texto_semaforo = clasificar_semaforo_stock(df_stock, df_consumo)

    if emoji == "🟢":
        st.success(f"{emoji} SEMÁFORO GENERAL: {texto_semaforo}")
    elif emoji == "🟡":
        st.warning(f"{emoji} SEMÁFORO GENERAL: {texto_semaforo}")
    else:
        st.error(f"{emoji} SEMÁFORO GENERAL: {texto_semaforo}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Consumo del día (kg)", kg_hoy)
    c2.metric("Barras consumidas hoy", barras_hoy)
    c3.metric("Metros del día", metros_hoy)
    c4.metric("Registros de hoy", len(consumo_hoy))

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
        if largo_barra_usada <= 0:
            st.error("No se puede guardar sin stock disponible.")
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

    if df_stock.empty:
        resumen_stock = pd.DataFrame(columns=["Diametro", "Cantidad Barras"])
    else:
        resumen_stock = (
            df_stock.groupby(["Diametro", "Largo Barra (m)"], dropna=False)["Cantidad Barras"]
            .sum()
            .reset_index()
            .sort_values(by=["Diametro", "Largo Barra (m)"])
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

    excel_file = generar_excel(df_stock, df_consumo, resumen_stock)

    st.download_button(
        label="📥 Descargar Excel",
        data=excel_file,
        file_name="control_fierro_terreno.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

st.markdown("---")
st.caption("Versión enfocada en consumo real de terreno, stock y semáforos.")
