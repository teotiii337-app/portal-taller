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

            # --- TABLA DERECHA: TESORERÍA ---
            with col_der:
                st.subheader("💰 Desglose de Cuentas")
                if not mi_tes.empty:
                    # Ordenar por fecha (si es posible, si no por orden de inserción invertido)
                    mi_tes = mi_tes.iloc[::-1] # Invertir orden para ver lo más nuevo arriba
                    
                    # Seleccionar columnas
                    display_tes = mi_tes[['Fecha', 'Concepto', 'Tipo', 'Monto']]
                    
                    # Formato condicional visual
                    def color_tipo(val):
                        color = 'red' if val == 'Cargo' else 'green'
                        return f'color: {color}; font-weight: bold'

                    st.dataframe(
                        display_tes.style.map(color_tipo, subset=['Tipo'])
                                   .format({"Monto": "${:,.2f}"}), # Formato moneda
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No hay movimientos registrados.")

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
        # VISTA: DETALLE TESORERÍA
        # ------------------------------------------
        elif menu == "Detalle Tesorería":
            st.header("Historial de Movimientos")
            ws_tes = sh.worksheet("TESORERIA")
            df_tes = pd.DataFrame(ws_tes.get_all_records())
            df_tes['ID_H'] = df_tes['ID_H'].astype(str)
            mi_tes = df_tes[df_tes['ID_H'] == st.session_state['id_h']]
            st.dataframe(mi_tes[['Fecha', 'Concepto', 'Tipo', 'Monto']], use_container_width=True)

        # ------------------------------------------
        # SECCIÓN ADMIN: PASE DE LISTA
        # ------------------------------------------
        elif menu == "ADMIN: Pase de Lista":
            st.header("📝 Pase de Lista")
            
            fecha_tenida = st.date_input("Fecha", datetime.today())
            grado_tenida = st.selectbox("Grado de Cámara", [1, 2, 3])
            
            ws_dir = sh.worksheet("DIRECTORIO")
            df_hh = pd.DataFrame(ws_dir.get_all_records())
            
            # Filtro: Mostrar solo HH con grado suficiente
            hh_aptos = df_hh[df_hh['Grado_Actual'] >= grado_tenida]
            
            # Filtro: Candidatos (Grado inferior)
            hh_candidatos = pd.DataFrame()
            if grado_tenida > 1:
                hh_candidatos = df_hh[df_hh['Grado_Actual'] == (grado_tenida - 1)]

            with st.form("form_lista"):
                st.subheader("Asistencia Regular")
                estados = {}
                for idx, row in hh_aptos.iterrows():
                    c1, c2 = st.columns([3,2])
                    c1.write(f"**{row['Nombre_Completo']}**")
                    estados[row['ID_H']] = c2.radio("Estado", ["Presente", "Falta", "Justif.", "Retardo"], key=row['ID_H'], horizontal=True, label_visibility="collapsed")
                    st.divider()
                
                ids_candidatos = []
                promocionar = False
                if not hh_candidatos.empty and grado_tenida > 1:
                    st.subheader("Candidatos / Ascensos")
                    dict_cand = {row['ID_H']: row['Nombre_Completo'] for idx, row in hh_candidatos.iterrows()}
                    ids_candidatos = st.multiselect("Seleccionar Candidatos presentes:", options=list(dict_cand.keys()), format_func=lambda x: dict_cand[x])
                    if ids_candidatos:
                        promocionar = st.checkbox(f"✅ Ascender automáticamente a {grado_tenida}º grado en Directorio")

                if st.form_submit_button("💾 Guardar Lista"):
                    ws_asis = sh.worksheet("ASISTENCIAS")
                    rows_to_add = []
                    
                    # Regulares
                    for id_h, estado in estados.items():
                        rows_to_add.append([fecha_tenida.strftime("%d/%m/%Y"), grado_tenida, str(id_h), estado, ""])
                    
                    # Candidatos
                    for id_can in ids_candidatos:
                        rows_to_add.append([fecha_tenida.strftime("%d/%m/%Y"), grado_tenida, str(id_can), "Presente", "Ceremonia Grado"])
                    
                    ws_asis.append_rows(rows_to_add)
                    
                    # Lógica de Promoción automática
                    if promocionar:
                        # Actualizar celda por celda (algo lento pero seguro)
                        cell_list = []
                        for id_can in ids_candidatos:
                            cell = ws_dir.find(str(id_can))
                            # Actualizar Grado (Col G=7)
                            ws_dir.update_cell(cell.row, 7, grado_tenida)
                            # Actualizar Fecha (I=9 o J=10)
                            col_fecha = 9 if grado_tenida == 2 else 10
                            ws_dir.update_cell(cell.row, col_fecha, fecha_tenida.strftime("%d/%m/%Y"))
                    
                    st.success("Lista guardada correctamente")

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
