import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Control Fierro Cristóbal", layout="wide")

# =========================
# CONFIG
# =========================
DIAMETROS = ["Ø8", "Ø10", "Ø12", "Ø16", "Ø18", "Ø22"]
LARGOS_BARRA = [6, 8, 9, 10, 11, 12]

COLUMNAS_BASE = [
    "Edificio",
    "Eje",
    "Elemento",
    "Diametro",
    "Largo Corte (m)",
    "Cantidad",
    "Estado",
    "Observacion"
]

# =========================
# FUNCIONES
# =========================
def inicializar_datos():
    if "df_items" not in st.session_state:
        st.session_state.df_items = pd.DataFrame(columns=COLUMNAS_BASE)

    if "df_stock" not in st.session_state:
        st.session_state.df_stock = pd.DataFrame({
            "Diametro": ["Ø8", "Ø10", "Ø12", "Ø16", "Ø18", "Ø22"],
            "Largo Barra (m)": [12, 12, 12, 12, 12, 12],
            "Cantidad Barras": [0, 0, 0, 0, 0, 0],
        })

def calcular_resumen(df_items, df_stock):
    if df_items.empty:
        return pd.DataFrame()

    df = df_items.copy()

    # Limpieza de tipos
    df["Largo Corte (m)"] = pd.to_numeric(df["Largo Corte (m)"], errors="coerce").fillna(0)
    df["Cantidad"] = pd.to_numeric(df["Cantidad"], errors="coerce").fillna(0)

    resumen = (
        df.groupby("Diametro", dropna=False)
        .agg(
            Piezas=("Cantidad", "sum"),
            Metros_Requeridos=("Largo Corte (m)", lambda x: 0)
        )
        .reset_index()
    )

    metros_req = (
        df.assign(Metros=df["Largo Corte (m)"] * df["Cantidad"])
        .groupby("Diametro", dropna=False)["Metros"]
        .sum()
        .reset_index()
        .rename(columns={"Metros": "Metros_Requeridos"})
    )

    resumen = resumen.drop(columns=["Metros_Requeridos"]).merge(
        metros_req, on="Diametro", how="left"
    )

    stock = df_stock.copy()
    stock["Largo Barra (m)"] = pd.to_numeric(stock["Largo Barra (m)"], errors="coerce").fillna(0)
    stock["Cantidad Barras"] = pd.to_numeric(stock["Cantidad Barras"], errors="coerce").fillna(0)
    stock["Metros_Stock"] = stock["Largo Barra (m)"] * stock["Cantidad Barras"]

    stock_res = (
        stock.groupby("Diametro", dropna=False)["Metros_Stock"]
        .sum()
        .reset_index()
    )

    resumen = resumen.merge(stock_res, on="Diametro", how="left")
    resumen["Metros_Stock"] = resumen["Metros_Stock"].fillna(0)
    resumen["Diferencia"] = resumen["Metros_Stock"] - resumen["Metros_Requeridos"]

    return resumen

def generar_excel(df_items, df_stock, df_resumen):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_items.to_excel(writer, index=False, sheet_name="Cortes")
        df_stock.to_excel(writer, index=False, sheet_name="Stock")
        df_resumen.to_excel(writer, index=False, sheet_name="Resumen")
    output.seek(0)
    return output

# =========================
# APP
# =========================
inicializar_datos()

st.title("🔩 Control Fierro Cristóbal")
st.caption("Versión estable sin lectura automática de PDF")

tab1, tab2, tab3, tab4 = st.tabs([
    "Ingreso Manual",
    "Tabla Editable",
    "Stock",
    "Resumen y Exportación"
])

# =========================
# TAB 1 - INGRESO MANUAL
# =========================
with tab1:
    st.subheader("Agregar corte manualmente")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        edificio = st.text_input("Edificio", value="")
        eje = st.text_input("Eje", value="")
    with col2:
        elemento = st.selectbox("Elemento", ["Muro", "Losa", "Viga", "Pilar", "Fundación", "Otro"])
        diametro = st.selectbox("Diámetro", DIAMETROS)
    with col3:
        largo_corte = st.number_input("Largo Corte (m)", min_value=0.0, step=0.01, format="%.2f")
        cantidad = st.number_input("Cantidad", min_value=1, step=1)
    with col4:
        estado = st.selectbox("Estado", ["Pendiente", "Preparado", "Instalado"])
        observacion = st.text_input("Observación", value="")

    if st.button("➕ Agregar corte"):
        nueva_fila = pd.DataFrame([{
            "Edificio": edificio,
            "Eje": eje,
            "Elemento": elemento,
            "Diametro": diametro,
            "Largo Corte (m)": largo_corte,
            "Cantidad": cantidad,
            "Estado": estado,
            "Observacion": observacion
        }])

        st.session_state.df_items = pd.concat(
            [st.session_state.df_items, nueva_fila],
            ignore_index=True
        )
        st.success("Corte agregado correctamente.")

# =========================
# TAB 2 - TABLA EDITABLE
# =========================
with tab2:
    st.subheader("Editar tabla de cortes")

    st.info("Aquí puedes pegar o corregir información manualmente.")

    df_editado = st.data_editor(
        st.session_state.df_items,
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("💾 Guardar cambios tabla"):
        st.session_state.df_items = df_editado.copy()
        st.success("Cambios guardados.")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🗑️ Limpiar todos los cortes"):
            st.session_state.df_items = pd.DataFrame(columns=COLUMNAS_BASE)
            st.success("Se eliminaron todos los cortes.")
            st.rerun()

    with col_b:
        archivo_excel = st.file_uploader(
            "Cargar cortes desde Excel",
            type=["xlsx"],
            key="excel_cortes"
        )

        if archivo_excel is not None:
            try:
                df_cargado = pd.read_excel(archivo_excel)
                st.session_state.df_items = df_cargado.copy()
                st.success("Excel cargado correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al cargar Excel: {e}")

# =========================
# TAB 3 - STOCK
# =========================
with tab3:
    st.subheader("Ingreso de stock")

    st.session_state.df_stock = st.data_editor(
        st.session_state.df_stock,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_stock"
    )

    st.markdown("### Agregar fila rápida de stock")

    c1, c2, c3 = st.columns(3)
    with c1:
        diam_stock = st.selectbox("Diámetro stock", DIAMETROS, key="diam_stock")
    with c2:
        largo_stock = st.selectbox("Largo barra (m)", LARGOS_BARRA, key="largo_stock")
    with c3:
        cant_stock = st.number_input("Cantidad barras", min_value=1, step=1, key="cant_stock")

    if st.button("➕ Agregar stock"):
        nueva_fila_stock = pd.DataFrame([{
            "Diametro": diam_stock,
            "Largo Barra (m)": largo_stock,
            "Cantidad Barras": cant_stock
        }])

        st.session_state.df_stock = pd.concat(
            [st.session_state.df_stock, nueva_fila_stock],
            ignore_index=True
        )
        st.success("Stock agregado.")
        st.rerun()

# =========================
# TAB 4 - RESUMEN
# =========================
with tab4:
    st.subheader("Resumen general")

    df_resumen = calcular_resumen(
        st.session_state.df_items,
        st.session_state.df_stock
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Total cortes", len(st.session_state.df_items))
    c2.metric(
        "Total piezas",
        int(pd.to_numeric(st.session_state.df_items.get("Cantidad", pd.Series()), errors="coerce").fillna(0).sum())
        if not st.session_state.df_items.empty else 0
    )
    c3.metric(
        "Total metros requeridos",
        round(
            (
                pd.to_numeric(st.session_state.df_items.get("Largo Corte (m)", pd.Series()), errors="coerce").fillna(0)
                * pd.to_numeric(st.session_state.df_items.get("Cantidad", pd.Series()), errors="coerce").fillna(0)
            ).sum(),
            2
        ) if not st.session_state.df_items.empty else 0
    )

    st.markdown("### Resumen por diámetro")
    st.dataframe(df_resumen, use_container_width=True)

    excel_file = generar_excel(
        st.session_state.df_items,
        st.session_state.df_stock,
        df_resumen
    )

    st.download_button(
        label="📥 Descargar Excel",
        data=excel_file,
        file_name="control_fierro_resumen.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.markdown("---")
st.caption("Versión sin lectura automática de PDF para mayor estabilidad.")
