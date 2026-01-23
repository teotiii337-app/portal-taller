import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import hashlib
from datetime import datetime
import time

# ==========================================
# CONFIGURACIÓN INICIAL Y CONEXIÓN
# ==========================================
st.set_page_config(page_title="Portal del Taller", page_icon="∴", layout="wide")

# Función de Seguridad (Hashing)
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hash(password) == hashed_text:
        return True
    return False

# Conexión a Google Sheets (Usando caché para velocidad)
@st.cache_resource
def connect_db():
    scope = ['https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive"]
    # Asegúrate de configurar los secretos en Streamlit Cloud
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    # IMPORTANTE: Reemplaza con el nombre EXACTO de tu archivo
    return client.open("Sec y Tes")

# ==========================================
# FUNCIONES DE LÓGICA DE NEGOCIO
# ==========================================

def get_user_data(username):
    sh = connect_db()
    ws = sh.worksheet("DIRECTORIO")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    user_row = df[df['Usuario'] == username]
    return user_row

def update_password(username, new_password):
    sh = connect_db()
    ws = sh.worksheet("DIRECTORIO")
    cell = ws.find(username)
    new_hash = make_hash(new_password)
    # Asumiendo Col D=Password (4) y Col E=Reset (5)
    ws.update_cell(cell.row, 4, new_hash)
    ws.update_cell(cell.row, 5, "FALSE")
    st.success("Contraseña actualizada. Por favor reingresa.")

# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================

def main():
    # Inicializar estado de sesión
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # ------------------------------------------
    # PANTALLA DE LOGIN
    # ------------------------------------------
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.title("∴ Acceso al Taller")
            st.markdown("---")
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type='password')
            
            if st.button("Entrar", use_container_width=True):
                try:
                    user_df = get_user_data(username)
                    if not user_df.empty:
                        stored_hash = user_df.iloc[0]['Password']
                        # Manejo de booleanos que vienen de Excel (TRUE/FALSE strings)
                        reset_val = str(user_df.iloc[0]['Reset_Requerido']).upper()
                        reset_required = (reset_val == 'TRUE')
                        
                        if check_hashes(password, stored_hash):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = username
                            st.session_state['role'] = user_df.iloc[0]['Rol'] # Admin o Miembro
                            st.session_state['reset'] = reset_required
                            st.session_state['id_h'] = str(user_df.iloc[0]['ID_H']) # ID como string
                            st.session_state['nombre'] = user_df.iloc[0]['Nombre_Completo']
                            st.session_state['grado_actual'] = int(user_df.iloc[0]['Grado_Actual'])
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
                    else:
                        st.error("Usuario no encontrado.")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")

    # ------------------------------------------
    # PANTALLA DE USUARIO LOGUEADO
    # ------------------------------------------
    else:
        # 1. CAMBIO DE CONTRASEÑA OBLIGATORIO
        if st.session_state['reset']:
            st.warning("⚠️ Por seguridad, debes configurar tu contraseña personal.")
            new_pass = st.text_input("Nueva Contraseña", type="password")
            confirm_pass = st.text_input("Confirmar Contraseña", type="password")
            if st.button("Guardar"):
                if new_pass == confirm_pass and len(new_pass) > 4:
                    update_password(st.session_state['username'], new_pass)
                    st.session_state['logged_in'] = False
                    st.rerun()
                else:
                    st.error("Las contraseñas no coinciden o son muy cortas.")
            return

        # 2. BARRA LATERAL (MENÚ)
        st.sidebar.title(f"H:. {st.session_state['nombre']}")
        st.sidebar.caption(f"Grado: {st.session_state['grado_actual']}º")
        
        opciones_menu = ["Mi Tablero (Resumen)", "Detalle Asistencias", "Detalle Tesorería"]
        if st.session_state['role'] == "Admin":
            opciones_menu.extend(["ADMIN: Pase de Lista", "ADMIN: Tesorería General", "ADMIN: Alta HH:."])
        
        menu = st.sidebar.radio("Navegación", opciones_menu)
        
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

        sh = connect_db()

        # ------------------------------------------
        # VISTA: MI TABLERO (RESUMEN DETALLADO)
        # ------------------------------------------
        if menu == "Mi Tablero (Resumen)":
            st.title(f"∴ Tablero del H:. {st.session_state['nombre']}")
            st.markdown("---")

            # 1. RECUPERAR DATOS (TESORERÍA Y ASISTENCIA)
            # Tesorería
            ws_tes = sh.worksheet("TESORERIA")
            df_tes = pd.DataFrame(ws_tes.get_all_records())
            df_tes['ID_H'] = df_tes['ID_H'].astype(str)
            mi_tes = df_tes[df_tes['ID_H'] == st.session_state['id_h']]

            # Asistencia
            ws_asis = sh.worksheet("ASISTENCIAS")
            df_asis = pd.DataFrame(ws_asis.get_all_records())
            # Si la hoja está vacía o no tiene datos del H, manejamos el error
            if not df_asis.empty:
                df_asis['ID_H'] = df_asis['ID_H'].astype(str)
                mis_asis = df_asis[df_asis['ID_H'] == st.session_state['id_h']]
            else:
                mis_asis = pd.DataFrame(columns=['Fecha_Tenida', 'Estado', 'Grado_Tenida'])

            # 2. CÁLCULOS DE SALDOS Y ESTADÍSTICAS
            # Limpieza de datos numéricos (quitamos signos de $ o comas si existen)
            try:
                mi_tes['Monto'] = pd.to_numeric(mi_tes['Monto'])
            except:
                pass # Si falla es porque ya es numérico o está vacío

            total_cargos = mi_tes[mi_tes['Tipo'] == 'Cargo']['Monto'].sum()
            total_abonos = mi_tes[mi_tes['Tipo'] == 'Abono']['Monto'].sum()
            saldo = total_cargos - total_abonos
            
            # Cálculo de Cápitas Pendientes (Asumiendo cápita de $450)
            MONTO_CAPITA = 450
            num_capitas = 0
            if saldo > 0:
                num_capitas = int(saldo / MONTO_CAPITA)

            # Cálculo Asistencia
            porcentaje = 0.0
            if not mis_asis.empty:
                total_reg = len(mis_asis)
                # Contamos Presente y Retardo como asistencia positiva
                asistencias = len(mis_asis[mis_asis['Estado'].isin(['Presente', 'Retardo', 'Comisión'])])
                if total_reg > 0:
                    porcentaje = (asistencias / total_reg) * 100

            # 3. TARJETAS DE RESUMEN (KPIs)
            kpi1, kpi2, kpi3 = st.columns(3)
            
            with kpi1:
                st.metric("Asistencia Global", f"{porcentaje:.1f}%", help="Calculado sobre Tenidas convocadas")
            
            with kpi2:
                # Color dinámico: Rojo si debe, Verde si tiene saldo a favor
                if saldo > 0:
                    st.metric("Saldo Pendiente", f"${saldo:,.2f}", f"-{num_capitas} Cápitas aprox.", delta_color="inverse")
                elif saldo == 0:
                    st.metric("Estatus", "A Plomo ($0.00)", delta_color="normal")
                else:
                    st.metric("Saldo a Favor", f"${abs(saldo):,.2f}", delta_color="normal")
            
            with kpi3:
                st.metric("Total Pagado (Histórico)", f"${total_abonos:,.2f}")

            st.markdown("---")

            # 4. TABLAS DE DETALLE (LADO A LADO)
            col_izq, col_der = st.columns([1, 1])

            # --- TABLA IZQUIERDA: ASISTENCIAS ---
            with col_izq:
                st.subheader("📅 Historial Asistencia")
                if not mis_asis.empty:
                    # Ordenar por fecha (asumiendo formato dd/mm/yyyy)
                    # Convertimos a datetime solo para ordenar, luego mostramos texto
                    mis_asis['Fecha_DT'] = pd.to_datetime(mis_asis['Fecha_Tenida'], dayfirst=True, errors='coerce')
                    mis_asis = mis_asis.sort_values(by='Fecha_DT', ascending=False)
                    
                    # Seleccionamos columnas para mostrar
                    display_asis = mis_asis[['Fecha_Tenida', 'Estado', 'Grado_Tenida']]
                    
                    # Colorear según estado (Truco visual de Pandas)
                    def color_estado(val):
                        color = 'black'
                        if val == 'Presente': color = 'green'
                        elif val == 'Falta': color = 'red'
                        elif val == 'Retardo': color = 'orange'
                        elif val == 'Justif.': color = 'blue'
                        return f'color: {color}'

                    st.dataframe(
                        display_asis.style.map(color_estado, subset=['Estado']),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No tienes registros de asistencia aún.")

# --- TABLA DERECHA: TESORERÍA (CON ESTADO DE CUENTA INTELIGENTE) ---
            with col_der:
                st.subheader("💰 Estado de Cuenta Detallado")
                
                if not mi_tes.empty:
                    # 1. Separar Cargos y Abonos
                    # Aseguramos que los montos sean numéricos
                    mi_tes['Monto'] = pd.to_numeric(mi_tes['Monto'], errors='coerce').fillna(0)
                    
                    cargos = mi_tes[mi_tes['Tipo'] == 'Cargo'].copy()
                    total_pagado = mi_tes[mi_tes['Tipo'] == 'Abono']['Monto'].sum()
                    
                    # 2. Lógica FIFO (El dinero paga la deuda más vieja primero)
                    data_estado_cuenta = []
                    dinero_disponible = total_pagado
                    
                    # Ordenamos cargos del más viejo al más nuevo para irlos pagando en orden
                    # (Asumiendo que insertas en orden cronológico, si no, habría que ordenar por fecha)
                    for index, row in cargos.iterrows():
                        monto_deuda = row['Monto']
                        estado = ""
                        pagado_aqui = 0
                        saldo_pendiente = 0
                        
                        if dinero_disponible >= monto_deuda:
                            # Alcanza para pagar toda esta deuda
                            estado = "Pagado"
                            pagado_aqui = monto_deuda
                            saldo_pendiente = 0
                            dinero_disponible -= monto_deuda
                        elif dinero_disponible > 0:
                            # Alcanza para pagar solo una parte (Abono parcial)
                            estado = "Parcial"
                            pagado_aqui = dinero_disponible
                            saldo_pendiente = monto_deuda - dinero_disponible
                            dinero_disponible = 0
                        else:
                            # Ya no hay dinero para esta deuda
                            estado = "Adeudo"
                            pagado_aqui = 0
                            saldo_pendiente = monto_deuda
                            
                        data_estado_cuenta.append({
                            "Fecha": row['Fecha'],
                            "Concepto": row['Concepto'],
                            "Costo": monto_deuda,
                            "Estatus": estado,
                            "Falta": saldo_pendiente
                        })
                    
                    # Crear DataFrame para visualizar
                    df_visual = pd.DataFrame(data_estado_cuenta)
                    
                    # Si no hay cargos pero hay saldo a favor (dinero extra)
                    if df_visual.empty and total_pagado > 0:
                        st.success(f"No tienes deudas registradas. Tienes un saldo a favor de ${total_pagado:,.2f}")
                    
                    elif not df_visual.empty:
                        # Invertimos el orden para mostrar lo más reciente arriba en la tabla (Enero abajo, Marzo arriba)
                        df_visual = df_visual.iloc[::-1]

                        # 3. Formato Visual con Colores (Pandas Styler)
                        def estilo_status(val):
                            color = 'red'
                            weight = 'normal'
                            if val == 'Pagado':
                                color = 'green'
                            elif val == 'Parcial':
                                color = 'orange'
                                weight = 'bold'
                            return f'color: {color}; font-weight: {weight}'

                        st.dataframe(
                            df_visual.style.map(estilo_status, subset=['Estatus'])
                                     .format({"Costo": "${:,.0f}", "Falta": "${:,.0f}"}), # Formato moneda sin centavos para limpieza
                            column_order=("Fecha", "Concepto", "Estatus", "Falta"), # Ocultamos "Costo" para no saturar, o puedes agregarlo
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        # Mostrar Saldo a Favor remanente si sobró dinero después de pagar todo
                        if dinero_disponible > 0:
                            st.caption(f"✨ Tienes un saldo a favor adicional de: **${dinero_disponible:,.2f}**")
                            
                else:
                    st.info("Sin movimientos.")
        # ------------------------------------------
        # VISTA: DETALLE ASISTENCIAS
        # ------------------------------------------
        elif menu == "Detalle Asistencias":
            st.header("Historial de Asistencias")
            ws_asis = sh.worksheet("ASISTENCIAS")
            df_asis = pd.DataFrame(ws_asis.get_all_records())
            df_asis['ID_H'] = df_asis['ID_H'].astype(str)
            mis_asis = df_asis[df_asis['ID_H'] == st.session_state['id_h']]
            st.dataframe(mis_asis[['Fecha_Tenida', 'Grado_Tenida', 'Estado', 'Observaciones']], use_container_width=True)

# ------------------------------------------
        # VISTA: DETALLE TESORERÍA (CON CRUCE DE FECHAS)
        # ------------------------------------------
        elif menu == "Detalle Tesorería":
            st.title("💰 Historial y Estado de Cuenta")
            st.markdown("---")
            
            # 1. Cargar datos y asegurar formato correcto
            ws_tes = sh.worksheet("TESORERIA")
            df_tes = pd.DataFrame(ws_tes.get_all_records())
            
            # Forzar que ID sea string para comparar bien
            df_tes['ID_H'] = df_tes['ID_H'].astype(str)
            mi_tes = df_tes[df_tes['ID_H'] == st.session_state['id_h']]

            if not mi_tes.empty:
                # Asegurar numéricos
                mi_tes['Monto'] = pd.to_numeric(mi_tes['Monto'], errors='coerce').fillna(0)
                
                # Pestañas
                tab_edo, tab_recibos = st.tabs(["📊 Estado de Adeudos", "🧾 Historial de Pagos"])
                
                # --- PESTAÑA 1: ESTADO DE CUENTA INTELIGENTE ---
                with tab_edo:
                    st.info("Aquí ves cómo tus pagos han ido cubriendo tus deudas mes a mes.")
                    
                    # Separamos Cargos y Abonos
                    cargos = mi_tes[mi_tes['Tipo'] == 'Cargo'].copy()
                    abonos = mi_tes[mi_tes['Tipo'] == 'Abono'].copy()
                    
                    # Convertimos a listas de diccionarios para procesar fácil
                    # Es vital que los abonos estén ordenados por fecha para aplicar FIFO (Primero entra, primero paga)
                    # Aquí asumimos orden de inserción (Excel), si quisieras por fecha estricta habría que ordenar.
                    cola_abonos = []
                    for _, row in abonos.iterrows():
                        cola_abonos.append({
                            'fecha': row['Fecha'], 
                            'monto_disponible': row['Monto']
                        })
                    
                    data_estado_cuenta = []
                    
                    # Recorremos cada deuda para ver con qué se paga
                    for _, row_cargo in cargos.iterrows():
                        monto_deuda = row_cargo['Monto']
                        saldo_deuda = monto_deuda
                        
                        detalles_pago = [] # Aquí guardaremos "Pagado $X el [Fecha]"
                        
                        # Mientras la deuda siga viva y tenga dinero en los abonos...
                        while saldo_deuda > 0 and cola_abonos:
                            abono_actual = cola_abonos[0] # Tomamos el abono más viejo disponible
                            
                            if abono_actual['monto_disponible'] > saldo_deuda:
                                # El abono cubre toda la deuda y sobra
                                detalles_pago.append(f"${saldo_deuda:,.0f} ({abono_actual['fecha']})")
                                abono_actual['monto_disponible'] -= saldo_deuda
                                saldo_deuda = 0
                            elif abono_actual['monto_disponible'] == saldo_deuda:
                                # El abono cubre exacto
                                detalles_pago.append(f"${saldo_deuda:,.0f} ({abono_actual['fecha']})")
                                saldo_deuda = 0
                                cola_abonos.pop(0) # Ese abono se acabó
                            else:
                                # El abono no alcanza, paga lo que tiene y se acaba
                                pagado = abono_actual['monto_disponible']
                                detalles_pago.append(f"${pagado:,.0f} ({abono_actual['fecha']})")
                                saldo_deuda -= pagado
                                cola_abonos.pop(0) # Pasamos al siguiente abono
                        
                        # Determinar estado final de esa fila
                        if saldo_deuda == 0:
                            estatus = "Pagado"
                        elif saldo_deuda < monto_deuda:
                            estatus = "Parcial"
                        else:
                            estatus = "Adeudo"
                            
                        # Formatear el texto de detalle
                        if detalles_pago:
                            texto_pagos = ", ".join(detalles_pago)
                        else:
                            texto_pagos = "-"

                        data_estado_cuenta.append({
                            "Fecha Cargo": row_cargo['Fecha'],
                            "Concepto": row_cargo['Concepto'],
                            "Monto": monto_deuda,
                            "Abonado": (monto_deuda - saldo_deuda),
                            "Saldo Pendiente": saldo_deuda,
                            "Estatus": estatus,
                            "Detalle Pagos": texto_pagos
                        })
                    
                    # VISUALIZACIÓN
                    df_visual = pd.DataFrame(data_estado_cuenta)
                    
                    if not df_visual.empty:
                        # Invertimos para ver lo más reciente arriba
                        df_visual = df_visual.iloc[::-1]
                        
                        def estilo_completo(val):
                            if val == 'Pagado': return 'color: green'
                            if val == 'Parcial': return 'color: orange; font-weight: bold'
                            return 'color: red'

                        st.dataframe(
                            df_visual.style.map(estilo_completo, subset=['Estatus'])
                                     .format({
                                         "Monto": "${:,.2f}", 
                                         "Abonado": "${:,.2f}", 
                                         "Saldo Pendiente": "${:,.2f}"
                                     }),
                            column_order=("Fecha Cargo", "Concepto", "Estatus", "Saldo Pendiente", "Detalle Pagos"),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("No tienes deudas registradas.")
                        
                    # Checar si sobró dinero en el último abono
                    remanente = sum(a['monto_disponible'] for a in cola_abonos)
                    if remanente > 0:
                        st.success(f"✨ Tienes un saldo a favor disponible de: **${remanente:,.2f}**")

                # --- PESTAÑA 2: TABLA SIMPLE DE ABONOS ---
                with tab_recibos:
                    st.caption("Lista simple de tus abonos registrados")
                    st.dataframe(abonos[['Fecha', 'Concepto', 'Monto']], use_container_width=True, hide_index=True)

            else:
                st.info("Sin movimientos en Tesorería.")
        # ------------------------------------------
        # SECCIÓN ADMIN: PASE DE LISTA
        # ------------------------------------------
# ---------------------------------------------------------
        # VISTA ADMIN: SECRETARÍA (PASE DE LISTA + REPORTES + KARDEX)
        # ---------------------------------------------------------
        elif menu == "ADMIN: Pase de Lista":
            st.header("📜 Secretaría y Archivo")
            
            # AHORA SON 3 PESTAÑAS
            tab_lista, tab_reporte, tab_kardex = st.tabs(["📝 Pase de Lista", "📊 Reporte Global", "📂 Expediente H:."])

            # --- TAB 1: PASE DE LISTA (OPERATIVO) ---
            with tab_lista:
                st.subheader("Registrar Asistencia del Día")
                fecha_tenida = st.date_input("Fecha de la Tenida", datetime.today())
                grado_tenida = st.selectbox("Grado de Trabajos", [1, 2, 3])
                
                ws_dir = sh.worksheet("DIRECTORIO")
                df_hh = pd.DataFrame(ws_dir.get_all_records())
                
                # Filtros
                hh_aptos = df_hh[df_hh['Grado_Actual'] >= grado_tenida]
                hh_cand = df_hh[df_hh['Grado_Actual'] == (grado_tenida - 1)] if grado_tenida > 1 else pd.DataFrame()

                with st.form("form_lista_secre"):
                    st.caption(f"Convocados: {len(hh_aptos)} HH:.")
                    # Lista Regular
                    estados = {}
                    for _, row in hh_aptos.iterrows():
                        c1, c2 = st.columns([3,2])
                        c1.markdown(f"**{row['Nombre_Completo']}**")
                        estados[row['ID_H']] = c2.radio("Edo", ["Presente", "Falta", "Justif.", "Retardo"], key=f"list_{row['ID_H']}", horizontal=True, label_visibility="collapsed")
                        st.divider()
                    
                    # Lista Candidatos
                    ids_cand = []
                    promocionar = False
                    if not hh_cand.empty:
                        st.info("🎓 Candidatos / Ascensos")
                        opciones_cand = {r['ID_H']: r['Nombre_Completo'] for _, r in hh_cand.iterrows()}
                        ids_cand = st.multiselect("Candidatos presentes:", list(opciones_cand.keys()), format_func=lambda x: opciones_cand[x])
                        if ids_cand:
                            promocionar = st.checkbox(f"✅ Ascender a {grado_tenida}º grado (Actualizar Directorio)")

                    if st.form_submit_button("💾 Guardar Asistencia"):
                        ws_asis = sh.worksheet("ASISTENCIAS")
                        rows = []
                        for id_h, est in estados.items():
                            rows.append([fecha_tenida.strftime("%d/%m/%Y"), grado_tenida, str(id_h), est, ""])
                        for id_c in ids_cand:
                            rows.append([fecha_tenida.strftime("%d/%m/%Y"), grado_tenida, str(id_c), "Presente", "Ceremonia Grado"])
                        
                        if rows: ws_asis.append_rows(rows)
                        
                        if promocionar and ids_cand:
                            records = ws_dir.get_all_records()
                            for i, rec in enumerate(records):
                                if str(rec['ID_H']) in ids_cand:
                                    ws_dir.update_cell(i + 2, 7, grado_tenida) # Col G
                                    col_f = 9 if grado_tenida == 2 else 10
                                    ws_dir.update_cell(i + 2, col_f, fecha_tenida.strftime("%d/%m/%Y"))
                            st.success("Grados actualizados.")
                        st.success("Asistencia guardada.")

            # --- TAB 2: REPORTE GENERAL ---
            with tab_reporte:
                st.subheader("Semáforo de Asistencia")
                ws_asis = sh.worksheet("ASISTENCIAS")
                df_asis = pd.DataFrame(ws_asis.get_all_records())
                ws_dir = sh.worksheet("DIRECTORIO")
                df_dir = pd.DataFrame(ws_dir.get_all_records())
                activos = df_dir[df_dir['Estatus'] == 'Activo']

                if not df_asis.empty:
                    df_asis['ID_H'] = df_asis['ID_H'].astype(str)
                    stats = []
                    for _, h in activos.iterrows():
                        uid = str(h['ID_H'])
                        regs = df_asis[df_asis['ID_H'] == uid]
                        total = len(regs)
                        asis = len(regs[regs['Estado'].isin(['Presente', 'Retardo', 'Comisión'])])
                        faltas = len(regs[regs['Estado'] == 'Falta'])
                        pct = (asis / total * 100) if total > 0 else 0
                        stats.append({"Nombre": h['Nombre_Completo'], "Grado": h['Grado_Actual'], "% Asist": pct, "Total": total, "❌": faltas})
                    
                    df_stats = pd.DataFrame(stats).sort_values(by="% Asist")
                    def color(v): return 'color: red; font-weight: bold' if v < 50 else ('color: green' if v >= 80 else 'color: orange')
                    st.dataframe(df_stats.style.format({"% Asist": "{:.1f}%"}).map(color, subset=['% Asist']), use_container_width=True, hide_index=True)
                else:
                    st.info("No hay datos.")

            # --- TAB 3: EXPEDIENTE INDIVIDUAL (LO NUEVO) ---
            with tab_kardex:
                st.subheader("📂 Expediente del Hermano")
                
                # 1. Selector de Hermano
                ws_dir = sh.worksheet("DIRECTORIO")
                nombres = ws_dir.col_values(2)[1:] # Nombres
                ids = ws_dir.col_values(1)[1:] # IDs
                dic_hh = dict(zip(nombres, ids))
                
                seleccionado = st.selectbox("Buscar Hermano:", nombres)
                id_sel = str(dic_hh[seleccionado])
                
                if seleccionado:
                    st.markdown("---")
                    
                    # 2. Obtener Datos Generales
                    df_dir = pd.DataFrame(ws_dir.get_all_records())
                    df_dir['ID_H'] = df_dir['ID_H'].astype(str)
                    info_h = df_dir[df_dir['ID_H'] == id_sel].iloc[0]
                    
                    # 3. Obtener Datos Financieros
                    ws_tes = sh.worksheet("TESORERIA")
                    df_tes = pd.DataFrame(ws_tes.get_all_records())
                    df_tes['ID_H'] = df_tes['ID_H'].astype(str)
                    mi_tes = df_tes[df_tes['ID_H'] == id_sel]
                    
                    saldo = 0
                    if not mi_tes.empty:
                        mi_tes['Monto'] = pd.to_numeric(mi_tes['Monto'], errors='coerce').fillna(0)
                        saldo = mi_tes[mi_tes['Tipo'] == 'Cargo']['Monto'].sum() - mi_tes[mi_tes['Tipo'] == 'Abono']['Monto'].sum()

                    # 4. Obtener Datos Asistencia
                    ws_asis = sh.worksheet("ASISTENCIAS")
                    df_asis = pd.DataFrame(ws_asis.get_all_records())
                    pct_asis = 0
                    total_asis = 0
                    if not df_asis.empty:
                        df_asis['ID_H'] = df_asis['ID_H'].astype(str)
                        mis_asis = df_asis[df_asis['ID_H'] == id_sel]
                        total_asis = len(mis_asis)
                        positivas = len(mis_asis[mis_asis['Estado'].isin(['Presente', 'Retardo'])])
                        if total_asis > 0:
                            pct_asis = (positivas / total_asis) * 100
                    
                    # --- VISTA DEL EXPEDIENTE ---
                    
                    # A. ENCABEZADO (DATOS BIOGRÁFICOS)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Grado", f"{info_h['Grado_Actual']}º")
                    c2.metric("Estatus", info_h['Estatus'])
                    c3.metric("Usuario", info_h['Usuario'])
                    c4.metric("ID", f"#{info_h['ID_H']}")
                    
                    # Fechas Importantes (Expandible)
                    with st.expander("📅 Fechas Masónicas (Iniciación, Aumento, Exaltación)"):
                        f1, f2, f3 = st.columns(3)
                        f1.write(f"**Iniciación:** {info_h['Fecha_Inic']}")
                        f2.write(f"**Aumento:** {info_h['Fecha_Aum'] if info_h['Fecha_Aum'] else '-'}")
                        f3.write(f"**Exaltación:** {info_h['Fecha_Exal'] if info_h['Fecha_Exal'] else '-'}")

                    st.divider()

                    # B. BLOQUE DE ESTADÍSTICAS (FINANZAS Y ASISTENCIA)
                    col_fin, col_asis = st.columns(2)
                    
                    with col_fin:
                        st.markdown("### 💰 Tesorería")
                        if saldo > 0:
                            st.error(f"Adeudo Total: **${saldo:,.2f}**")
                            st.caption(f"Equivale a aprox. {int(saldo/450)} cápitas.")
                        elif saldo == 0:
                            st.success("Al corriente ($0.00)")
                        else:
                            st.success(f"Saldo a Favor: ${abs(saldo):,.2f}")
                        
                        # Tabla mini de últimos 3 movimientos
                        if not mi_tes.empty:
                            st.caption("Últimos movimientos:")
                            st.dataframe(mi_tes.tail(3)[['Fecha', 'Concepto', 'Tipo', 'Monto']], use_container_width=True, hide_index=True)

                    with col_asis:
                        st.markdown("### 📝 Asistencia")
                        st.metric("Porcentaje Histórico", f"{pct_asis:.1f}%")
                        st.write(f"Ha asistido a **{int((pct_asis/100)*total_asis)}** de **{total_asis}** convocatorias.")
                        
                        # Tabla mini de últimas 3 faltas (si las hay)
                        if not df_asis.empty:
                            faltas = mis_asis[mis_asis['Estado'] == 'Falta']
                            if not faltas.empty:
                                st.caption("Últimas Faltas:")
                                st.dataframe(faltas.tail(3)[['Fecha_Tenida', 'Grado_Tenida']], use_container_width=True, hide_index=True)
                            else:
                                st.caption("¡Sin faltas registradas!")

        # ------------------------------------------
        # SECCIÓN ADMIN: TESORERÍA GENERAL (V.M. y TES.)
        # ------------------------------------------
        elif menu == "ADMIN: Tesorería General":
            st.header("⚖️ Balance del Taller")
            
            # Pestañas internas
            tab1, tab2, tab3 = st.tabs(["Balance General", "Registrar Pago H:.", "Registrar Gasto/Salida"])
            
            # --- TAB 1: BALANCE ---
            with tab1:
                ws_caja = sh.worksheet("LIBRO_CAJA")
                df_caja = pd.DataFrame(ws_caja.get_all_records())
                
                total_entradas = pd.to_numeric(df_caja['Entrada']).sum()
                total_salidas = pd.to_numeric(df_caja['Salida']).sum()
                saldo_real = total_entradas - total_salidas
                
                # Cuentas por Cobrar (Deuda de HH)
                ws_tes_global = sh.worksheet("TESORERIA")
                df_tg = pd.DataFrame(ws_tes_global.get_all_records())
                total_deuda_hh = pd.to_numeric(df_tg[df_tg['Tipo'] == 'Cargo']['Monto']).sum() - pd.to_numeric(df_tg[df_tg['Tipo'] == 'Abono']['Monto']).sum()

                m1, m2, m3 = st.columns(3)
                m1.metric("Dinero en Caja (Real)", f"${saldo_real:,.2f}")
                m2.metric("Cuentas por Cobrar (Deuda)", f"${total_deuda_hh:,.2f}")
                m3.metric("Gastos Totales Históricos", f"${total_salidas:,.2f}")
                
                st.subheader("Movimientos Recientes de Caja")
                st.dataframe(df_caja.tail(10), use_container_width=True)

            # --- TAB 2: REGISTRAR PAGO DE UN HERMANO ---
            with tab2:
                st.info("Usa esto cuando un H:. pague Cápitas, Tronco, etc.")
                with st.form("pago_hh"):
                    fecha_pago = st.date_input("Fecha Pago", datetime.today())
                    ws_dir = sh.worksheet("DIRECTORIO")
                    lista_hh = ws_dir.col_values(2)[1:] # Nombres
                    lista_ids = ws_dir.col_values(1)[1:] # IDs
                    dict_hh = dict(zip(lista_hh, lista_ids))
                    
                    nombre_selec = st.selectbox("Hermano que paga", lista_hh)
                    concepto = st.text_input("Concepto", "Pago Cápita")
                    monto = st.number_input("Monto Recibido", min_value=0.0, step=10.0)
                    
                    if st.form_submit_button("Registrar Ingreso"):
                        id_h = dict_hh[nombre_selec]
                        # 1. Registrar en Cuenta Individual (TESORERIA)
                        ws_tes = sh.worksheet("TESORERIA")
                        ws_tes.append_row([
                            fecha_pago.strftime("%d/%m/%Y"), str(id_h), concepto, "Abono", monto
                        ])
                        # 2. Registrar en Caja General (LIBRO_CAJA)
                        ws_caja = sh.worksheet("LIBRO_CAJA")
                        ws_caja.append_row([
                            fecha_pago.strftime("%d/%m/%Y"), f"{concepto} ({nombre_selec})", "Ingreso Interno", monto, 0, ""
                        ])
                        st.success("Pago registrado en ambas cuentas.")

            # --- TAB 3: REGISTRAR GASTO ---
            with tab3:
                st.error("Usa esto para Pagos a GL, Compras, Cenas, etc.")
                with st.form("gasto_gral"):
                    fecha_gasto = st.date_input("Fecha Gasto", datetime.today())
                    concepto_gasto = st.text_input("Concepto", "Pago a Gr:. Tes:.")
                    categoria = st.selectbox("Categoría", ["Gasto Operativo", "Pago a GL", "Evento/Fiesta", "Beneficencia"])
                    monto_gasto = st.number_input("Monto Pagado", min_value=0.0, step=10.0)
                    ref = st.text_input("Referencia/Factura (Opcional)")
                    
                    if st.form_submit_button("Registrar Salida"):
                        ws_caja = sh.worksheet("LIBRO_CAJA")
                        ws_caja.append_row([
                            fecha_gasto.strftime("%d/%m/%Y"), concepto_gasto, categoria, 0, monto_gasto, ref
                        ])
                        st.success("Gasto descontado de Caja General.")

        # ------------------------------------------
        # SECCIÓN ADMIN: ALTA DE HH (INICIACIÓN)
        # ------------------------------------------
        elif menu == "ADMIN: Alta HH:.":
            st.header("Alta de Neófito / Afiliado")
            with st.form("alta_user"):
                c1, c2 = st.columns(2)
                nuevo_id = c1.text_input("ID Nuevo (Ej: 035)")
                nuevo_nombre = c2.text_input("Nombre Completo")
                nuevo_user = c1.text_input("Usuario (Ej: jlopez)")
                nuevo_pass_temp = c2.text_input("Contraseña Temporal")
                fecha_ini = st.date_input("Fecha Iniciación", datetime.today())
                
                if st.form_submit_button("Crear Usuario"):
                    ws_dir = sh.worksheet("DIRECTORIO")
                    # Encriptar pass temporal
                    pass_hash = make_hash(nuevo_pass_temp)
                    # Agregar fila: ID, Nombre, User, Pass, Reset=TRUE, Rol=Miembro, Grado=1, Fecha...
                    ws_dir.append_row([
                        nuevo_id, nuevo_nombre, nuevo_user, pass_hash, "TRUE", "Miembro", 1, 
                        fecha_ini.strftime("%d/%m/%Y"), "", "", "Activo"
                    ])
                    st.success(f"H:. {nuevo_nombre} registrado. Dile que entre con '{nuevo_pass_temp}' para configurar su clave.")

if __name__ == '__main__':

    main()




