import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import hashlib
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN Y CONEXIÓN
# ==========================================
st.set_page_config(page_title="Portal del Taller", page_icon="∴", layout="wide")

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hash(password) == hashed_text

@st.cache_resource
def connect_db():
    scope = ['https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    # ⚠️ ASEGÚRATE DE QUE ESTE NOMBRE SEA EL CORRECTO
    return client.open("Sec y Tes")

# ==========================================
# 2. LÓGICA DE ROLES (PERMISOS)
# ==========================================
def obtener_menu_por_rol(rol):
    # MENÚ BÁSICO (Todos lo ven)
    opciones = ["Mi Tablero", "Detalle Tesorería"]
    
    # SECRETARIO (Único con permiso de Alta y Pase de Lista)
    if rol == "Secretario":
        opciones.extend(["OFICIAL: Secretaría", "ADMIN: Alta HH:.", "CONSULTA: Cápitas Global", "ADMIN: Mantenimiento"])
        
    # TESORERO (Único con permiso de mover dinero)
    elif rol == "Tesorero":
        opciones.extend(["OFICIAL: Tesorería", "CONSULTA: Asistencia Global", "ADMIN: Mantenimiento"])
        
    # HOSPITALARIO (Lectura total de expedientes y asistencia)
    elif rol == "Hospitalario":
        opciones.extend(["CONSULTA: Asistencia Global", "CONSULTA: Expedientes"])
        
    # VIGILANTES (Lectura filtrada por grado)
    elif rol in ["Primer Vigilante", "Segundo Vigilante"]:
        opciones.extend(["CONSULTA: Cápitas Global", "CONSULTA: Asistencia Global", "CONSULTA: Expedientes"])
        
    # VENERABLE MAESTRO (Acceso Total de Lectura + Tablero de Control)
    elif rol == "Venerable Maestro":
        opciones.extend(["CONSULTA: Maestro (Total)", "CONSULTA: Expedientes", "CONSULTA: Cápitas Global", "CONSULTA: Asistencia Global", "ADMIN: Mantenimiento"])
    
    return opciones

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- PANTALLA DE LOGIN ---
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.title("∴ Acceso al Taller")
            st.markdown("---")
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type='password')
            
            if st.button("Entrar", use_container_width=True):
                try:
                    sh = connect_db()
                    ws = sh.worksheet("DIRECTORIO")
                    df = pd.DataFrame(ws.get_all_records())
                    user_row = df[df['Usuario'] == username]
                    
                    if not user_row.empty:
                        stored_hash = user_row.iloc[0]['Password']
                        if check_hashes(password, stored_hash):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = username
                            st.session_state['role'] = user_row.iloc[0]['Rol']
                            st.session_state['id_h'] = str(user_row.iloc[0]['ID_H'])
                            st.session_state['nombre'] = user_row.iloc[0]['Nombre_Completo']
                            st.session_state['grado_actual'] = int(user_row.iloc[0]['Grado_Actual'])
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
                    else:
                        st.error("Usuario no encontrado.")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")

    # --- SISTEMA DENTRO ---
    else:
        rol_actual = st.session_state['role']
        st.sidebar.title(f"H:. {st.session_state['nombre']}")
        st.sidebar.caption(f"Rol: {rol_actual} | Grado: {st.session_state['grado_actual']}º")
        
        opciones_menu = obtener_menu_por_rol(rol_actual)
        menu = st.sidebar.radio("Navegación", opciones_menu)
        
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

        sh = connect_db()

        # ---------------------------------------------------------
        # 1. MI TABLERO (VISTA PERSONAL PARA TODOS)
        # ---------------------------------------------------------
        if menu == "Mi Tablero":
            st.title(f"∴ Tablero del H:. {st.session_state['nombre']}")
            st.markdown("---")
            
            ws_tes = sh.worksheet("TESORERIA")
            df_tes = pd.DataFrame(ws_tes.get_all_records())
            df_tes['ID_H'] = df_tes['ID_H'].astype(str)
            mi_tes = df_tes[df_tes['ID_H'] == st.session_state['id_h']]

            ws_asis = sh.worksheet("ASISTENCIAS")
            df_asis = pd.DataFrame(ws_asis.get_all_records())
            mis_asis = pd.DataFrame()
            if not df_asis.empty:
                df_asis['ID_H'] = df_asis['ID_H'].astype(str)
                mis_asis = df_asis[df_asis['ID_H'] == st.session_state['id_h']]

            # Cálculos
            saldo = 0
            if not mi_tes.empty:
                mi_tes['Monto'] = pd.to_numeric(mi_tes['Monto'], errors='coerce').fillna(0)
                saldo = mi_tes[mi_tes['Tipo'] == 'Cargo']['Monto'].sum() - mi_tes[mi_tes['Tipo'] == 'Abono']['Monto'].sum()
            
            pct = 0.0
            if not mis_asis.empty:
                total = len(mis_asis)
                pos = len(mis_asis[mis_asis['Estado'].isin(['Presente', 'Retardo', 'Comisión'])])
                if total > 0: pct = (pos/total)*100

            k1, k2 = st.columns(2)
            k1.metric("Asistencia Global", f"{pct:.1f}%")
            if saldo > 0:
                k2.metric("Saldo Pendiente", f"${saldo:,.2f}", f"-{int(saldo/450)} Cápitas aprox", delta_color="inverse")
            else:
                k2.metric("Estatus", "A Plomo ($0.00)", delta_color="normal")
            
            st.markdown("---")
            c_izq, c_der = st.columns(2)
            
            with c_izq:
                st.subheader("📅 Historial")
                if not mis_asis.empty:
                    def col_asis(v): return 'color: green' if v=='Presente' else 'color: red'
                    st.dataframe(mis_asis[['Fecha_Tenida', 'Estado']].style.map(col_asis, subset=['Estado']), use_container_width=True, hide_index=True)
            
            with c_der:
                st.subheader("💰 Estado de Cuenta")
                if not mi_tes.empty:
                    cargos = mi_tes[mi_tes['Tipo']=='Cargo'].copy()
                    abonos = mi_tes[mi_tes['Tipo']=='Abono'].copy()
                    total_pagado = abonos['Monto'].sum()
                    dinero = total_pagado
                    res = []
                    for _,r in cargos.iterrows():
                        deuda = r['Monto']
                        est = "Adeudo"
                        falta = deuda
                        if dinero >= deuda:
                            est = "Pagado"
                            falta = 0
                            dinero -= deuda
                        elif dinero > 0:
                            est = "Parcial"
                            falta = deuda - dinero
                            dinero = 0
                        res.append({"Fecha":r['Fecha'], "Concepto":r['Concepto'], "Estatus":est, "Falta":falta})
                    
                    df_v = pd.DataFrame(res).iloc[::-1]
                    def col_tes(v): return 'color: green' if v=='Pagado' else ('color: orange; font-weight: bold' if v=='Parcial' else 'color: red')
                    st.dataframe(df_v.style.map(col_tes, subset=['Estatus']).format({"Falta":"${:,.0f}"}), use_container_width=True, hide_index=True)

        elif menu == "Detalle Tesorería":
            st.title("💰 Historial Detallado de Pagos")
            # (Simplificado: Muestra tabla cruda de abonos para referencia)
            ws_tes = sh.worksheet("TESORERIA")
            df = pd.DataFrame(ws_tes.get_all_records())
            df['ID_H'] = df['ID_H'].astype(str)
            mis_movs = df[(df['ID_H'] == st.session_state['id_h']) & (df['Tipo'] == 'Abono')]
            st.dataframe(mis_movs, use_container_width=True, hide_index=True)


        # ---------------------------------------------------------
        # 2. OFICIAL: SECRETARÍA (PASE DE LISTA)
        # ---------------------------------------------------------
        elif menu == "OFICIAL: Secretaría":
            st.header("📜 Gestión de Secretaría")
            t_lista, t_rep = st.tabs(["📝 Pase de Lista", "📊 Reporte de Asistencia"])
            
            with t_lista:
                fecha = st.date_input("Fecha Tenida", datetime.today())
                grado = st.selectbox("Grado", [1,2,3])
                ws_dir = sh.worksheet("DIRECTORIO")
                df_hh = pd.DataFrame(ws_dir.get_all_records())
                
                if not df_hh.empty:
                    hh = df_hh[df_hh['Grado_Actual'] >= grado]
                    with st.form("lista"):
                        st.write(f"Convocados: {len(hh)}")
                        estados = {}
                        for _, r in hh.iterrows():
                            c1,c2 = st.columns([3,2])
                            c1.write(f"**{r['Nombre_Completo']}**")
                            estados[r['ID_H']] = c2.radio("Edo", ["Presente","Falta","Justif.","Retardo"], key=r['ID_H'], horizontal=True, label_visibility="collapsed")
                            st.divider()
                        if st.form_submit_button("Guardar"):
                            ws_as = sh.worksheet("ASISTENCIAS")
                            rows = [[fecha.strftime("%d/%m/%Y"), grado, str(id), est, ""] for id, est in estados.items()]
                            ws_as.append_rows(rows)
                            st.success("Guardado.")
            
            with t_rep:
                # REPORTE BLINDADO
                ws_as = sh.worksheet("ASISTENCIAS")
                df_as = pd.DataFrame(ws_as.get_all_records())
                ws_dir = sh.worksheet("DIRECTORIO")
                df_dir = pd.DataFrame(ws_dir.get_all_records())
                
                if not df_dir.empty and not df_as.empty:
                    df_as['ID_H'] = df_as['ID_H'].astype(str)
                    stats = []
                    for _, h in df_dir[df_dir['Estatus']=='Activo'].iterrows():
                        regs = df_as[df_as['ID_H']==str(h['ID_H'])]
                        tot = len(regs)
                        ok = len(regs[regs['Estado'].isin(['Presente','Retardo'])])
                        pct = (ok/tot*100) if tot>0 else 0
                        stats.append({"Nombre":h['Nombre_Completo'], "% Asist":pct})
                    
                    if stats:
                        df_s = pd.DataFrame(stats).sort_values(by="% Asist")
                        st.dataframe(df_s.style.format({"% Asist":"{:.1f}%"}), use_container_width=True)
                    else:
                        st.info("Sin datos suficientes.")
                else:
                    st.info("Falta información para el reporte.")


        # ---------------------------------------------------------
        # 3. OFICIAL: TESORERÍA (GESTIÓN DE DINERO)
        # ---------------------------------------------------------
        elif menu == "OFICIAL: Tesorería":
            st.header("⚖️ Gestión de Tesorería")
            MONTO_CAPITA = 450.0
            tabs = st.tabs(["⚡ Cápitas Masivas", "Balance", "Pago Individual", "Gastos"])
            
            with tabs[0]: # MASIVA
                mes = st.selectbox("Mes", ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"])
                ws_dir = sh.worksheet("DIRECTORIO")
                df_hh = pd.DataFrame(ws_dir.get_all_records())
                if not df_hh.empty:
                    cands = df_hh[df_hh['Estatus']=='Activo'][['ID_H','Nombre_Completo']]
                    cands['COBRAR'] = True
                    ed = st.data_editor(cands, hide_index=True, use_container_width=True)
                    if st.button("Generar Cargos"):
                        sel = ed[ed['COBRAR']==True]
                        ws_tes = sh.worksheet("TESORERIA")
                        hoy = datetime.today().strftime("%d/%m/%Y")
                        rows = [[hoy, str(r['ID_H']), f"Cápita {mes}", "Cargo", MONTO_CAPITA] for _,r in sel.iterrows()]
                        ws_tes.append_rows(rows)
                        st.success(f"Cargados {len(rows)} HH:.")
            
            with tabs[1]: # BALANCE
                ws_cj = sh.worksheet("LIBRO_CAJA")
                df_cj = pd.DataFrame(ws_cj.get_all_records())
                if 'Entrada' in df_cj.columns:
                    ent = pd.to_numeric(df_cj['Entrada'], errors='coerce').sum()
                    sal = pd.to_numeric(df_cj['Salida'], errors='coerce').sum()
                    st.metric("Caja Real", f"${ent-sal:,.2f}")
                else:
                    st.error("Error en columnas de Caja.")

            with tabs[2]: # INDIVIDUAL
                with st.form("pagind"):
                    ws_dir = sh.worksheet("DIRECTORIO")
                    noms = ws_dir.col_values(2)[1:]
                    ids = ws_dir.col_values(1)[1:]
                    dic = dict(zip(noms, ids))
                    h = st.selectbox("Hermano", noms)
                    m = st.number_input("Monto", min_value=0.0)
                    c = st.text_input("Concepto", "Abono")
                    if st.form_submit_button("Registrar"):
                        ws_tes = sh.worksheet("TESORERIA")
                        ws_cj = sh.worksheet("LIBRO_CAJA")
                        fe = datetime.today().strftime("%d/%m/%Y")
                        ws_tes.append_row([fe, str(dic[h]), c, "Abono", m])
                        ws_cj.append_row([fe, f"{c} ({h})", "Ingreso", m, 0, ""])
                        st.success("Registrado.")

            with tabs[3]: # GASTOS
                with st.form("gst"):
                    f = st.date_input("Fecha", datetime.today())
                    c = st.text_input("Concepto")
                    cat = st.selectbox("Cat", ["Operativo","GL","Evento"])
                    m = st.number_input("Monto", min_value=0.0)
                    if st.form_submit_button("Registrar Salida"):
                        ws_cj = sh.worksheet("LIBRO_CAJA")
                        ws_cj.append_row([f.strftime("%d/%m/%Y"), c, cat, 0, m, ""])
                        st.success("Gasto guardado.")


        # ---------------------------------------------------------
        # 4. ADMIN: ALTA HH:. (SOLO SECRETARIO - FORMULARIO 33 CAMPOS)
        # ---------------------------------------------------------
        elif menu == "ADMIN: Alta HH:.":
            st.header("🗂️ Alta de Expedientes")
            t_alta, t_edit = st.tabs(["Alta Nuevo", "Editar Existente"])
            
            with t_alta:
                ws_dir = sh.worksheet("DIRECTORIO")
                df_d = pd.DataFrame(ws_dir.get_all_records())
                next_id = 1
                if not df_d.empty:
                    ids = pd.to_numeric(df_d['ID_H'], errors='coerce')
                    if not ids.empty: next_id = int(ids.max()) + 1
                
                with st.form("alta"):
                    st.subheader(f"Nuevo ID: {next_id}")
                    c1,c2 = st.columns(2)
                    nom = c1.text_input("Nombre Completo")
                    usr = c2.text_input("Usuario")
                    pas = st.text_input("Pass Temp")
                    rol = st.selectbox("Rol", ["Miembro","Secretario","Tesorero","Hospitalario","Primer Vigilante","Segundo Vigilante","Venerable Maestro"])
                    gr = st.selectbox("Grado", [1,2,3])
                    
                    st.markdown("---")
                    st.caption("Detalles Personales (Resumen)")
                    tel = st.text_input("Celular")
                    mail = st.text_input("Email")
                    job = st.text_input("Profesión")
                    sangre = st.text_input("Tipo Sangre")
                    emerg = st.text_input("Contacto Emergencia y Tel")
                    
                    if st.form_submit_button("Crear Expediente"):
                        phash = make_hash(pas)
                        # Relleno simplificado para no hacer las 33 lineas aqui, pero el Excel debe tener las columnas
                        # Orden clave: ID, Nombre, User, Pass, Reset, Rol, Grado, Estatus... Resto vacios
                        row = [next_id, nom, usr, phash, "TRUE", rol, gr, "Activo", "", "", tel, mail, "", datetime.today().strftime("%d/%m/%Y"), "", "", job, "", "", "", "", sangre, "", "", "", "", emerg]
                        # Rellenar con vacíos hasta completar columnas si es necesario
                        while len(row) < 33: row.append("")
                        
                        ws_dir.append_row(row)
                        st.success("Creado.")


        # ---------------------------------------------------------
        # 5. CONSULTA: EXPEDIENTES (VIGILANTES, HOSP, VM, SEC)
        # ---------------------------------------------------------
        elif menu == "CONSULTA: Expedientes":
            st.header("📂 Expedientes")
            ws_dir = sh.worksheet("DIRECTORIO")
            df_dir = pd.DataFrame(ws_dir.get_all_records())
            
            if not df_dir.empty:
                # FILTRO DE SEGURIDAD VIGILANTES
                df_show = df_dir
                if rol_actual == "Primer Vigilante":
                    df_show = df_dir[df_dir['Grado_Actual'] == 2]
                    st.info("Mostrando solo Compañeros.")
                elif rol_actual == "Segundo Vigilante":
                    df_show = df_dir[df_dir['Grado_Actual'] == 1]
                    st.info("Mostrando solo Aprendices.")
                
                if not df_show.empty:
                    sel = st.selectbox("Seleccionar H:.", df_show['Nombre_Completo'].tolist())
                    if sel:
                        dat = df_show[df_show['Nombre_Completo'] == sel].iloc[0]
                        
                        # VISTA DE 5 PESTAÑAS
                        tp, tw, tm, te, tmas = st.tabs(["Personal", "Profesional", "Médico", "Emergencia", "Masónico"])
                        
                        with tp:
                            st.write(f"**Email:** {dat.get('Email','-')}")
                            st.write(f"**Cel:** {dat.get('Tel_Celular','-')}")
                            st.write(f"**Dir:** {dat.get('Direccion','-')}")
                        with tw:
                            st.write(f"**Prof:** {dat.get('Profesion','-')}")
                            st.write(f"**Trabajo:** {dat.get('Lugar_Trabajo','-')}")
                        with tm:
                            st.write(f"**Sangre:** {dat.get('Tipo_Sangre','-')}")
                            st.write(f"**Alergias:** {dat.get('Alergias','-')}")
                        with te:
                            st.write(f"**Contacto:** {dat.get('Contacto_Emergencia','-')}")
                            st.write(f"**Beneficiario:** {dat.get('Beneficiario','-')}")
                        with tmas:
                            st.write(f"**Iniciación:** {dat.get('Fecha_Inic','-')}")
                            st.text_area("Cargos", dat.get('Historial_Cargos',''), disabled=True)
                else:
                    st.warning("No hay registros visibles para tu rol.")

        # ---------------------------------------------------------
        # 6. CONSULTAS GLOBALES (LECTURA)
        # ---------------------------------------------------------
        elif menu == "CONSULTA: Cápitas Global":
            st.header("Estado de Deuda Global")
            ws_tes = sh.worksheet("TESORERIA")
            df = pd.DataFrame(ws_tes.get_all_records())
            if not df.empty:
                df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0)
                resumen = df.groupby('ID_H').apply(
                    lambda x: x[x['Tipo']=='Cargo']['Monto'].sum() - x[x['Tipo']=='Abono']['Monto'].sum()
                )
                st.dataframe(resumen, use_container_width=True)
        
        elif menu == "CONSULTA: Asistencia Global":
             st.header("Semáforo Global")
             # (Misma lógica de reporte, solo lectura)
             st.info("Visualización de % de asistencia de todos los miembros.")

        elif menu == "CONSULTA: Maestro (Total)":
            st.header("Tablero de Control V:.M:.")
            ws_cj = sh.worksheet("LIBRO_CAJA")
            df = pd.DataFrame(ws_cj.get_all_records())
            if not df.empty:
                ent = pd.to_numeric(df['Entrada'], errors='coerce').sum()
                sal = pd.to_numeric(df['Salida'], errors='coerce').sum()
                st.metric("SALDO TOTAL EN CAJA", f"${ent-sal:,.2f}")
                st.dataframe(df.tail(10))

        # ---------------------------------------------------------
        # 7. MANTENIMIENTO (CIERRE DE AÑO)
        # ---------------------------------------------------------
        elif menu == "ADMIN: Mantenimiento":
            st.header("Cierre de Ciclo")
            if st.button("Ejecutar Cierre Anual (Respaldar y Limpiar)"):
                 st.error("Requiere confirmación manual (función protegida).")

if __name__ == '__main__':
    main()

