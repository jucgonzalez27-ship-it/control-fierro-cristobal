import re
from itertools import combinations
from datetime import datetime

import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="Control Fierro Cristobal", layout="wide")

# =========================
# CONFIG
# =========================
DIAMETROS = ["Ø8", "Ø10", "Ø12", "Ø16", "Ø18", "Ø22", "Ø25"]
LARGOS = [6, 8, 10, 11, 12]

PESOS = {
    "Ø8": 0.395,
    "Ø10": 0.617,
    "Ø12": 0.888,
    "Ø16": 1.58,
    "Ø18": 2.00,
    "Ø22": 2.98,
    "Ø25": 3.85,
}

STOCK_MIN = {
    "Ø8": 10,
    "Ø10": 10,
    "Ø12": 12,
    "Ø16": 10,
    "Ø18": 8,
    "Ø22": 6,
    "Ø25": 4,
}

ELEMENTOS = ["Losa", "Muro", "Viga", "Pilar", "Capitel", "Rampa", "Fundación", "Otro"]
ESTADOS_AVANCE = ["Pendiente", "En corte", "Cortado", "Instalado", "Terminado"]


# =========================
# SESSION
# =========================
if "plan_preliminar" not in st.session_state:
    st.session_state.plan_preliminar = pd.DataFrame(columns=[
        "edificio",
        "nivel",
        "eje",
        "elemento",
        "diametro",
        "cantidad",
        "largo_unitario",
        "largo_total",
        "kg",
    ])

if "plan" not in st.session_state:
    st.session_state.plan = pd.DataFrame(columns=[
        "id_plan",
        "edificio",
        "nivel",
        "eje",
        "elemento",
        "diametro",
        "cantidad",
        "largo_unitario",
        "largo_total",
        "kg",
        "ejecutado",
        "pendiente",
        "estado",
    ])

if "avances" not in st.session_state:
    st.session_state.avances = []

if "stock" not in st.session_state:
    st.session_state.stock = {d: 0 for d in DIAMETROS}

if "cantidad_temp" not in st.session_state:
    st.session_state.cantidad_temp = 0


# =========================
# HELPERS PDF
# =========================
def extraer_texto_pdf(pdf_file) -> str:
    reader = PdfReader(pdf_file)
    texto = []
    for page in reader.pages:
        contenido = page.extract_text()
        if contenido:
            texto.append(contenido)
    return "\n".join(texto)


def normalizar_diametro(valor: str) -> str:
    valor = str(valor).strip()
    if valor.startswith("Ø"):
        return valor
    if valor.isdigit():
        return f"Ø{valor}"
    return valor


def intentar_parsear_cubicacion(texto: str) -> pd.DataFrame:
    """
    Parser inicial aproximado.
    No busca perfección; busca dejar una tabla preliminar editable.
    """
    filas = []
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]

    for linea in lineas:
        if "Edificio" not in linea:
            continue

        tokens = linea.split()
        if len(tokens) < 8:
            continue

        try:
            edificio = ""
            if tokens[0] == "Edificio" and len(tokens) > 1:
                edificio = f"{tokens[0]} {tokens[1]}"
            else:
                continue

            eje = tokens[2] if len(tokens) > 2 else ""
            elemento = tokens[3] if len(tokens) > 3 else ""

            nums = re.findall(r"\d+,\d+|\d+", linea)

            diametro = ""
            diametros_posibles = {"8", "10", "12", "16", "18", "22", "25"}
            for n in nums:
                limpio = n.replace(",", ".")
                if limpio.isdigit() and limpio in diametros_posibles:
                    diametro = normalizar_diametro(limpio)
                    break

            cantidad = None
            if diametro:
                d = diametro.replace("Ø", "")
                idx_d = None
                for i, t in enumerate(tokens):
                    if t == d:
                        idx_d = i
                        break
                if idx_d is not None and idx_d + 1 < len(tokens):
                    try:
                        cantidad = int(tokens[idx_d + 1])
                    except Exception:
                        cantidad = None

            decimales = re.findall(r"\d+,\d+", linea)
            largo_total = None
            kg = None
            if len(decimales) >= 2:
                largo_total = float(decimales[-2].replace(",", "."))
                kg = float(decimales[-1].replace(",", "."))

            nivel = ""
            enteros = re.findall(r"\b\d+\b", linea)
            if enteros:
                nivel = enteros[-2] if len(enteros) >= 2 else ""

            largo_unitario = None
            if cantidad and largo_total:
                largo_unitario = round(largo_total / cantidad, 2)

            if eje and elemento and diametro and cantidad:
                filas.append({
                    "edificio": edificio,
                    "nivel": nivel,
                    "eje": eje,
                    "elemento": elemento,
                    "diametro": diametro,
                    "cantidad": cantidad,
                    "largo_unitario": largo_unitario,
                    "largo_total": largo_total,
                    "kg": kg,
                })

        except Exception:
            continue

    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.drop_duplicates().reset_index(drop=True)
    return df


def validar_plan(df: pd.DataFrame) -> list[str]:
    errores = []

    for i, row in df.iterrows():
        if not str(row.get("eje", "")).strip():
            errores.append(f"Fila {i+1}: falta eje")
        if not str(row.get("elemento", "")).strip():
            errores.append(f"Fila {i+1}: falta elemento")
        if not str(row.get("diametro", "")).strip():
            errores.append(f"Fila {i+1}: falta diámetro")

        try:
            cantidad = float(row.get("cantidad", 0))
            if cantidad <= 0:
                errores.append(f"Fila {i+1}: cantidad inválida")
        except Exception:
            errores.append(f"Fila {i+1}: cantidad inválida")

    return errores


# =========================
# HELPERS PLAN / AVANCE
# =========================
def asegurar_plan_id(df_plan: pd.DataFrame) -> pd.DataFrame:
    df_plan = df_plan.copy()
    if "id_plan" not in df_plan.columns:
        df_plan.insert(0, "id_plan", range(1, len(df_plan) + 1))
    return df_plan


def recalcular_plan_con_avances():
    if st.session_state.plan.empty:
        return

    plan = st.session_state.plan.copy()

    if st.session_state.avances:
        df_av = pd.DataFrame(st.session_state.avances)
        ejec = df_av.groupby("id_plan", as_index=False)["cantidad_ejecutada"].sum()
        ejec = ejec.rename(columns={"cantidad_ejecutada": "ejecutado_real"})
        plan = plan.drop(columns=[c for c in ["ejecutado_real"] if c in plan.columns], errors="ignore")
        plan = plan.merge(ejec, on="id_plan", how="left")
        plan["ejecutado_real"] = plan["ejecutado_real"].fillna(0)
    else:
        plan["ejecutado_real"] = 0

    plan["ejecutado"] = plan["ejecutado_real"]
    plan["pendiente"] = plan["cantidad"] - plan["ejecutado"]
    plan["pendiente"] = plan["pendiente"].apply(lambda x: max(x, 0))

    def estado_fila(row):
        if row["ejecutado"] <= 0:
            return "Pendiente"
        if row["ejecutado"] < row["cantidad"]:
            return "En corte"
        if row["ejecutado"] == row["cantidad"]:
            return "Instalado"
        return "Sobreconsumo"

    plan["estado"] = plan.apply(estado_fila, axis=1)
    plan = plan.drop(columns=["ejecutado_real"], errors="ignore")
    st.session_state.plan = plan


def agregar_avance(id_plan, fecha, cantidad_ejecutada, responsable, observacion):
    st.session_state.avances.append({
        "fecha": pd.to_datetime(fecha),
        "id_plan": int(id_plan),
        "cantidad_ejecutada": int(cantidad_ejecutada),
        "responsable": responsable,
        "observacion": observacion,
    })
    recalcular_plan_con_avances()


def get_df_avances() -> pd.DataFrame:
    if not st.session_state.avances:
        return pd.DataFrame(columns=["fecha", "id_plan", "cantidad_ejecutada", "responsable", "observacion"])
    return pd.DataFrame(st.session_state.avances)


def obtener_resumen_stock():
    consumo_por_diametro = {d: 0 for d in DIAMETROS}

    if not st.session_state.plan.empty:
        plan = st.session_state.plan
        agrupado = plan.groupby("diametro")["ejecutado"].sum().to_dict()
        for d in DIAMETROS:
            consumo_por_diametro[d] = int(agrupado.get(d, 0))

    filas = []
    for d in DIAMETROS:
        stock_inicial = st.session_state.stock[d]
        usado = consumo_por_diametro[d]
        disponible = stock_inicial - usado
        estado = "Crítico" if disponible <= STOCK_MIN[d] else "OK"
        filas.append({
            "diametro": d,
            "stock_inicial": stock_inicial,
            "consumido": usado,
            "disponible": disponible,
            "estado_stock": estado,
        })

    return pd.DataFrame(filas)


def generar_alertas_inteligentes():
    alertas = []

    df_av = get_df_avances()
    plan = st.session_state.plan

    if not df_av.empty:
        consumo_dia = df_av.groupby(df_av["fecha"].dt.date)["cantidad_ejecutada"].sum()

        if len(consumo_dia) > 2:
            promedio = consumo_dia.mean()
            hoy = consumo_dia.iloc[-1]
            if promedio > 0 and hoy > promedio * 1.5:
                alertas.append(f"Consumo anormal hoy: {int(hoy)} unidades vs promedio {int(promedio)}.")

    if not plan.empty:
        sobre = plan[plan["ejecutado"] > plan["cantidad"]]
        for _, row in sobre.iterrows():
            alertas.append(
                f"Sobreconsumo en Eje {row['eje']} / {row['elemento']} / {row['diametro']}: "
                f"plan {int(row['cantidad'])}, ejecutado {int(row['ejecutado'])}."
            )

        pendientes = plan[plan["estado"] == "Pendiente"]
        if len(pendientes) > 0:
            top_pend = pendientes.head(5)
            for _, row in top_pend.iterrows():
                alertas.append(
                    f"Sin avance: Eje {row['eje']} / {row['elemento']} / {row['diametro']} "
                    f"({int(row['cantidad'])} unidades planificadas)."
                )

    stock_df = obtener_resumen_stock()
    for _, row in stock_df.iterrows():
        if row["disponible"] <= STOCK_MIN[row["diametro"]]:
            alertas.append(
                f"Stock bajo en {row['diametro']}: quedan {int(row['disponible'])} unidades."
            )

    return alertas


# =========================
# HELPERS OPTIMIZADOR
# =========================
def calcular_plan_corte(piezas, barra):
    restante = piezas.copy()
    plan = []

    while restante:
        mejor_local = []
        mejor_sobrante = barra

        for r in range(1, len(restante) + 1):
            for comb in combinations(restante, r):
                total = sum(comb)
                if total <= barra:
                    sobrante = barra - total
                    if sobrante < mejor_sobrante:
                        mejor_local = comb
                        mejor_sobrante = sobrante

        if not mejor_local:
            break

        plan.append(mejor_local)

        for x in mejor_local:
            restante.remove(x)

    return plan


# =========================
# UI
# =========================
st.title("🧱 Control Fierro Pro")
st.caption("Carga de cubicación PDF, plan de ejecución, avance real, stock, alertas y optimización.")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📥 Carga de plan",
    "📋 Plan de ejecución",
    "⚡ Registro de avance",
    "📦 Stock y alertas",
    "✂️ Optimización",
    "📄 Reporte",
])

# =========================
# TAB 1 CARGA DE PLAN
# =========================
with tab1:
    st.subheader("Carga de cubicación PDF")
    st.caption("Sube el PDF, revisa la tabla preliminar y confirma el plan.")

    archivo_pdf = st.file_uploader("Subir PDF de cubicación", type=["pdf"])
    c1, c2 = st.columns(2)
    procesar = c1.button("Procesar PDF", use_container_width=True)
    limpiar = c2.button("Limpiar tabla", use_container_width=True)

    if limpiar:
        st.session_state.plan_preliminar = pd.DataFrame(columns=[
            "edificio", "nivel", "eje", "elemento", "diametro",
            "cantidad", "largo_unitario", "largo_total", "kg"
        ])
        st.session_state.plan = pd.DataFrame(columns=[
            "id_plan", "edificio", "nivel", "eje", "elemento", "diametro",
            "cantidad", "largo_unitario", "largo_total", "kg",
            "ejecutado", "pendiente", "estado"
        ])
        st.session_state.avances = []
        st.rerun()

    if procesar:
        if archivo_pdf is None:
            st.error("Debes subir un PDF.")
        else:
            texto = extraer_texto_pdf(archivo_pdf)
            df_pre = intentar_parsear_cubicacion(texto)
            if df_pre.empty:
                st.warning("No se detectaron filas útiles automáticamente. Puedes cargar la tabla manualmente.")
            st.session_state.plan_preliminar = df_pre

    st.markdown("### Tabla preliminar editable")
    df_editado = st.data_editor(
        st.session_state.plan_preliminar,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_plan",
    )

    errores = validar_plan(df_editado) if not df_editado.empty else []

    st.markdown("### Validación")
    if df_editado.empty:
        st.info("Todavía no hay datos para validar.")
    else:
        if errores:
            for e in errores:
                st.error(e)
        else:
            st.success("Tabla lista para confirmar.")

    if st.button("✅ Confirmar plan de ejecución", use_container_width=True):
        if df_editado.empty:
            st.error("No hay datos para confirmar.")
        else:
            errores = validar_plan(df_editado)
            if errores:
                st.error("Corrige los errores antes de confirmar el plan.")
            else:
                df_plan = df_editado.copy()
                df_plan = asegurar_plan_id(df_plan)
                df_plan["ejecutado"] = 0
                df_plan["pendiente"] = df_plan["cantidad"]
                df_plan["estado"] = "Pendiente"
                st.session_state.plan = df_plan
                st.success("Plan confirmado correctamente.")

    if not st.session_state.plan.empty:
        st.markdown("### Plan confirmado")
        st.dataframe(st.session_state.plan, use_container_width=True)

# =========================
# TAB 2 PLAN DE EJECUCIÓN
# =========================
with tab2:
    st.subheader("Plan de ejecución")
    st.caption("Qué deberías ejecutar según la cubicación confirmada.")

    if st.session_state.plan.empty:
        st.info("Primero confirma un plan en la pestaña de carga.")
    else:
        plan = st.session_state.plan.copy()

        f1, f2, f3, f4, f5 = st.columns(5)
        filtro_edificio = f1.selectbox("Edificio", ["Todos"] + sorted(plan["edificio"].dropna().astype(str).unique().tolist()))
        filtro_nivel = f2.selectbox("Nivel", ["Todos"] + sorted(plan["nivel"].dropna().astype(str).unique().tolist()))
        filtro_eje = f3.selectbox("Eje", ["Todos"] + sorted(plan["eje"].dropna().astype(str).unique().tolist()))
        filtro_elemento = f4.selectbox("Elemento", ["Todos"] + sorted(plan["elemento"].dropna().astype(str).unique().tolist()))
        filtro_diametro = f5.selectbox("Diámetro", ["Todos"] + sorted(plan["diametro"].dropna().astype(str).unique().tolist()))

        if filtro_edificio != "Todos":
            plan = plan[plan["edificio"].astype(str) == filtro_edificio]
        if filtro_nivel != "Todos":
            plan = plan[plan["nivel"].astype(str) == filtro_nivel]
        if filtro_eje != "Todos":
            plan = plan[plan["eje"].astype(str) == filtro_eje]
        if filtro_elemento != "Todos":
            plan = plan[plan["elemento"].astype(str) == filtro_elemento]
        if filtro_diametro != "Todos":
            plan = plan[plan["diametro"].astype(str) == filtro_diametro]

        if not plan.empty:
            plan["avance_%"] = (plan["ejecutado"] / plan["cantidad"] * 100).round(1)
            st.dataframe(plan, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("Ítems plan", len(plan))
            c2.metric("Cantidad planificada", int(plan["cantidad"].fillna(0).sum()))
            c3.metric("Cantidad ejecutada", int(plan["ejecutado"].fillna(0).sum()))
        else:
            st.info("No hay resultados con esos filtros.")

# =========================
# TAB 3 REGISTRO DE AVANCE
# =========================
with tab3:
    st.subheader("Registro rápido de avance")
    st.caption("Registra avance sobre ítems que ya vienen del plan.")

    if st.session_state.plan.empty:
        st.info("Primero confirma un plan.")
    else:
        plan = st.session_state.plan.copy()

        opciones = [
            f"{row['id_plan']} | {row['eje']} | {row['elemento']} | {row['diametro']} | Plan {int(row['cantidad'])} | Pendiente {int(row['pendiente'])}"
            for _, row in plan.iterrows()
        ]

        seleccion = st.selectbox("Selecciona ítem del plan", opciones)
        id_plan = int(seleccion.split("|")[0].strip())

        fila = plan[plan["id_plan"] == id_plan].iloc[0]

        st.info(
            f"Edificio: {fila['edificio']} | Nivel: {fila['nivel']} | "
            f"Eje: {fila['eje']} | Elemento: {fila['elemento']} | "
            f"Diámetro: {fila['diametro']}"
        )

        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=datetime.now())
        responsable = c2.text_input("Responsable")
        estado_manual = c3.selectbox("Estado manual", ESTADOS_AVANCE)

        st.markdown("### Cantidad rápida")
        b1, b2, b3, b4 = st.columns(4)

        if b1.button("+1", use_container_width=True):
            st.session_state.cantidad_temp += 1
        if b2.button("+5", use_container_width=True):
            st.session_state.cantidad_temp += 5
        if b3.button("+10", use_container_width=True):
            st.session_state.cantidad_temp += 10
        if b4.button("Limpiar", use_container_width=True):
            st.session_state.cantidad_temp = 0

        cantidad = st.number_input(
            "Cantidad de unidades ejecutadas",
            min_value=0,
            step=1,
            value=st.session_state.cantidad_temp,
        )

        observacion = st.text_area("Observación")

        if st.button("💾 Guardar avance", use_container_width=True):
            if not responsable.strip():
                st.error("Debes ingresar responsable.")
            elif cantidad <= 0:
                st.error("La cantidad debe ser mayor a 0.")
            else:
                agregar_avance(
                    id_plan=id_plan,
                    fecha=fecha,
                    cantidad_ejecutada=int(cantidad),
                    responsable=responsable.strip(),
                    observacion=f"[{estado_manual}] {observacion.strip()}",
                )
                st.session_state.cantidad_temp = 0
                st.success("Avance guardado correctamente.")
                st.rerun()

        df_av = get_df_avances()
        if not df_av.empty:
            st.markdown("### Últimos avances")
            st.dataframe(df_av.sort_values("fecha", ascending=False).head(20), use_container_width=True)

# =========================
# TAB 4 STOCK Y ALERTAS
# =========================
with tab4:
    st.subheader("Stock y alertas inteligentes")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Stock inicial por diámetro")
        for d in DIAMETROS:
            st.session_state.stock[d] = st.number_input(
                f"{d}",
                min_value=0,
                step=1,
                value=int(st.session_state.stock[d]),
                key=f"stock_{d}",
            )

    with c2:
        st.markdown("### Resumen stock")
        stock_df = obtener_resumen_stock()
        st.dataframe(stock_df, use_container_width=True)

    st.markdown("### Alertas")
    alertas = generar_alertas_inteligentes()

    if not alertas:
        st.success("Sin alertas relevantes por ahora.")
    else:
        for alerta in alertas:
            st.warning(alerta)

# =========================
# TAB 5 OPTIMIZACIÓN
# =========================
with tab5:
    st.subheader("Optimización de cortes")
    st.caption("Reduce pérdida de material en corte de barras.")

    barra = st.number_input("Largo barra madre (m)", value=12.0, step=0.5)
    modo = st.radio("Modo", ["Lista libre", "Cantidad por medida"])

    piezas = []

    if modo == "Lista libre":
        entrada = st.text_area("Ejemplo: 3.65,3.65,2.10,1.20")
        if entrada:
            try:
                piezas = [float(x.strip()) for x in entrada.split(",") if x.strip()]
            except Exception:
                st.error("Revisa el formato de la lista libre.")
    else:
        medidas = st.text_area("Ejemplo: 3.65=10,2.10=8")
        if medidas:
            try:
                for item in medidas.split(","):
                    m, c = item.split("=")
                    piezas += [float(m.strip())] * int(c.strip())
            except Exception:
                st.error("Revisa el formato de cantidad por medida.")

    if piezas:
        plan_corte = calcular_plan_corte(piezas, barra)

        st.markdown("### Plan completo")
        total_sobrante = 0.0

        for i, p in enumerate(plan_corte):
            sobrante = round(barra - sum(p), 2)
            total_sobrante += sobrante
            st.write(f"Barra {i+1}: {p} → sobrante {sobrante} m")

        st.success(f"Barras necesarias: {len(plan_corte)}")
        st.info(f"Sobrante total estimado: {round(total_sobrante, 2)} m")

# =========================
# TAB 6 REPORTE
# =========================
with tab6:
    st.subheader("Reporte automático PRO")

    plan = st.session_state.plan.copy()
    df_av = get_df_avances()

    if plan.empty:
        st.info("Todavía no hay plan confirmado.")
    else:
        total_plan = int(plan["cantidad"].fillna(0).sum())
        total_ejecutado = int(plan["ejecutado"].fillna(0).sum())

        total_kg = 0
        if "kg" in plan.columns:
            total_kg = int(plan["kg"].fillna(0).sum())

        texto = ""
        texto += "REPORTE DIARIO FIERRO\n"
        texto += "----------------------\n"
        texto += f"Total planificado: {total_plan}\n"
        texto += f"Total ejecutado: {total_ejecutado}\n"
        texto += f"Total kg plan: {total_kg}\n\n"

        resumen = plan.groupby(["eje", "elemento", "diametro"], as_index=False)[["cantidad", "ejecutado", "pendiente"]].sum()

        texto += "DETALLE PLAN VS REAL\n"
        for _, r in resumen.iterrows():
            texto += (
                f"- Eje {r['eje']} | {r['elemento']} | {r['diametro']} | "
                f"Plan: {int(r['cantidad'])} | Ejecutado: {int(r['ejecutado'])} | "
                f"Pendiente: {int(r['pendiente'])}\n"
            )

        texto += "\nALERTAS\n"
        alertas = generar_alertas_inteligentes()
        if not alertas:
            texto += "- Sin alertas relevantes\n"
        else:
            for a in alertas:
                texto += f"- {a}\n"

        st.text_area("Copiar reporte", texto, height=350)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total planificado", total_plan)
        c2.metric("Total ejecutado", total_ejecutado)
        c3.metric("Avance global %", round((total_ejecutado / total_plan * 100), 1) if total_plan > 0 else 0.0)