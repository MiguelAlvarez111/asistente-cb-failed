import pandas as pd
import requests
import io
import re
import streamlit as st
from datetime import datetime

# ==============================================================================
# SECCIÓN 1: CONFIGURACIÓN DE LA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Asistente CB Failed", layout="wide")

# ==============================================================================
# SECCIÓN 2: FUNCIONES DEL BOT (EL "CEREBRO")
# ==============================================================================

@st.cache_data
def get_npi_data(npi_number):
    if not npi_number or not str(npi_number).strip().isdigit(): return None
    npi_number = str(npi_number).strip()
    api_url = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi_number}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status(); data = response.json()
        if data.get('result_count', 0) > 0:
            provider = data['results'][0]; basic = provider.get('basic', {})
            first_name = basic.get('first_name', '')
            middle_name = basic.get('middle_name', '')
            name_parts = [first_name, middle_name]
            full_first_middle = ' '.join(part for part in name_parts if part)
            full_name = f"{basic.get('last_name', '')}, {full_first_middle} {basic.get('credential', '')}".strip()
            return {'full_name': full_name, 'npi': npi_number}
        return None
    except requests.exceptions.RequestException: return None

@st.cache_data
def load_dictionaries_by_filename(_uploaded_files):
    if not _uploaded_files: return {}
    st.info("Cargando diccionarios...")
    dictionaries = {}
    for uploaded_file in _uploaded_files:
        filename = uploaded_file.name
        try:
            df = pd.read_csv(uploaded_file, sep='|', header=0, encoding='latin1', low_memory=False, dtype=str).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            key_name = ''
            if 'Providers' in filename: key_name = 'providers'
            elif 'Surgeons' in filename: key_name = 'surgeons'
            elif 'Coder' in filename or 'DN35113' in filename: key_name = 'coders'
            if key_name:
                dictionaries[key_name] = df
                st.sidebar.write(f"✓ '{filename}' cargado como '{key_name}'.")
        except Exception as e: st.sidebar.error(f"Error al cargar '{filename}': {e}")
    return dictionaries

@st.cache_data
def parse_usap_corrections(_uploaded_files):
    if not _uploaded_files: return {}
    st.info("Procesando correcciones de USAP...")
    corrections = {}
    for uploaded_file in _uploaded_files:
        try:
            xls = pd.ExcelFile(uploaded_file)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str).fillna('')
                header_row_index = -1
                for i, row in df.iterrows():
                    row_str = ' '.join(row.values).lower()
                    if 'sin' in row_str and ('npi' in row_str or 'last - title' in row_str):
                        header_row_index = i; break
                if header_row_index == -1: continue
                df.columns = [str(c).strip().lower() for c in df.iloc[header_row_index]]
                df = df.iloc[header_row_index + 1:].reset_index(drop=True)
                if 'sin' in df.columns:
                    for index, row in df.iterrows():
                        sin_val = str(row.get('sin', '')).strip()
                        if not sin_val: continue
                        instruction = None
                        comment_raw = str(row.get('comments', '')); comment = comment_raw.lower()
                        npi_col_val = str(row.get('npi', '')); cb_col_val = str(row.get('cbcode', ''))
                        
                        match_chg_provider_cb = re.search(r"correct provider (.*?) with cb code (.*)", comment)
                        match_chg_provider_npi = re.search(r"correct provider (.*?) with npi (.*)", comment)
                        if 'chg to' in npi_col_val.lower():
                            instruction = {'type': 'change_ticket', 'new_name': npi_col_val.lower().replace('chg to', '').strip(), 'new_cb': cb_col_val}
                        elif match_chg_provider_cb:
                            instruction = {'type': 'change_ticket', 'new_name': match_chg_provider_cb.group(1).strip(), 'new_cb': match_chg_provider_cb.group(2).strip().rstrip(')')}
                        elif match_chg_provider_npi:
                            instruction = {'type': 'change_ticket', 'new_name': match_chg_provider_npi.group(1).strip(), 'new_npi': match_chg_provider_npi.group(2).strip()}
                        elif 'awaiting' in cb_col_val.lower() or 'pending' in comment:
                            instruction = {'type': 'awaiting'}
                        elif (cb_col_val and cb_col_val not in ['nan', '']) or (npi_col_val and npi_col_val not in ['nan', '']):
                            instruction = {'type': 'simple_correction', 'new_cb': cb_col_val if cb_col_val else None, 'new_npi': npi_col_val if npi_col_val else None}
                        
                        if instruction and (sin_val not in corrections or instruction['type'] != 'awaiting'):
                            corrections[sin_val] = instruction
        except Exception as e: st.sidebar.error(f"Error al procesar '{uploaded_file.name}': {e}")
    st.info(f"Se encontraron {len(corrections)} instrucciones de corrección.")
    return corrections

def find_provider(key, value, provider_type, dictionaries):
    value = str(value).replace('.0', '').strip()
    dict_structures = {
        'surgeons': {'npi_col': 'NPI_NUMBER', 'cb_col': 'NUMBER', 'name_cols': ['Lastname', 'Firstname', 'MiddleName']},
        'providers': {'npi_col': 'NPI_NUMBER', 'cb_col': 'ProvMnemonic', 'name_cols': ['LastName', 'FirstName', 'MiddleName']}
    }
    dict_keys_to_search = []
    if provider_type == "Surgeon or Provider": dict_keys_to_search = ['surgeons', 'providers']
    elif 'Surgeon' in provider_type: dict_keys_to_search = ['surgeons']
    elif 'Provider' in provider_type: dict_keys_to_search = ['providers']
    for dict_key in dict_keys_to_search:
        if dict_key in dictionaries:
            dict_df = dictionaries[dict_key]; structure = dict_structures.get(dict_key, {})
            if not structure: continue
            search_col_name = ''
            if key.upper() == 'NPI': search_col_name = structure['npi_col']
            elif key.upper() == 'CBCODE': search_col_name = structure['cb_col']
            if search_col_name and search_col_name in dict_df.columns:
                result = dict_df[dict_df[search_col_name].str.lower() == value.lower()]
                if not result.empty:
                    res = result.iloc[0]
                    name_parts = [res.get(c) for c in structure['name_cols'] if pd.notna(res.get(c))]
                    full_name = ' '.join(name_parts).strip()
                    return {'npi': res.get(structure['npi_col']), 'cbcode': res.get(structure['cb_col']), 'full_name_constructed': full_name}
    return None

def process_dataframe(df, dictionaries, corrections, learned_cb_codes):
    if 'Bot_Accion' not in df.columns: df.insert(5, 'Bot_Accion', '')
    if 'Sugerencias_Bot' not in df.columns: df.insert(6, 'Sugerencias_Bot', '')
    if 'Bot_Detalles' not in df.columns: df.insert(7, 'Bot_Detalles', '')
    if 'Source' not in df.columns: df.insert(8, 'Source', '')

    for index, row in df.iterrows():
        action, suggestion, details, source = "AWAITING USAP", "", "", "Bot Analysis"
        sin = str(row.get('SIN', '')).strip(); npi = str(row.get('NPI', '')).replace('.0', '').strip()
        provider_type = str(row.get('Type', ''))
        
        if sin in corrections:
            source = "USAP Correction"; corr = corrections[sin]; corr_type = corr.get('type')
            if corr_type == 'change_ticket':
                action = "CHANGE TICKET"; new_cb = corr.get('new_cb', '')
                if 'add to ge' in new_cb.lower():
                    suggestion = f"Cambiar por: {corr.get('new_name', '').upper()}"
                    details = f"El nuevo proveedor (NPI: {corr.get('new_npi')}) necesita ser añadido (ADD TO GE)."
                else:
                    provider_info = find_provider("CBCODE", new_cb, "Surgeon or Provider", dictionaries)
                    api_info = get_npi_data(provider_info['npi'] if provider_info else corr.get('new_npi'))
                    name_str = (provider_info['full_name_constructed'] if provider_info else corr.get('new_name', '')).upper()
                    suggestion = f"Cambiar por: {name_str}"
                    if provider_info: details += f"Info Dicc: {provider_info['full_name_constructed']} (NPI: {provider_info['npi']}, CB: {provider_info['cbcode']})\n"
                    if api_info: details += f"Info API: {api_info['full_name']}"
            elif corr_type == 'simple_correction':
                action = "COMPLETAR INFO"; npi_to_use = corr.get('new_npi') or npi; cb_to_use = corr.get('new_cb', '')
                if 'add to ge' in cb_to_use.lower():
                    action = "AWAITING USAP"; details = f"Instrucción 'ADD TO GE' para NPI {npi_to_use}."
                else:
                    suggestion = f"Agregar/Corregir NPI: {npi_to_use}, CBCode: {cb_to_use}"
                    dict_info = find_provider("NPI", npi_to_use, provider_type, dictionaries); api_info = get_npi_data(npi_to_use)
                    if dict_info: details += f"Info Dicc: {dict_info['full_name_constructed']} (CB: {dict_info['cbcode']})\n"
                    if api_info: details += f"Info API: {api_info['full_name']}"
        elif npi and npi in learned_cb_codes:
            action = "COMPLETAR INFO"; source = "Learned Correction"
            suggestion = f"Aplicar CBCode aprendido: {learned_cb_codes[npi]}"
            dict_info = find_provider("NPI", npi, provider_type, dictionaries); api_info = get_npi_data(npi)
            if dict_info: details += f"Info Dicc: {dict_info['full_name_constructed']} (CB: {dict_info['cbcode']})\n"
            if api_info: details += f"Info API: {api_info['full_name']}"
        elif npi and npi != 'nan':
            provider_info = find_provider('NPI', npi, provider_type, dictionaries)
            if provider_info:
                action = "COMPLETAR INFO"; source = "Dictionary"
                suggestion = f"CBCode encontrado: {provider_info['cbcode']}"
                api_info = get_npi_data(npi)
                if provider_info: details += f"Info Dicc: {provider_info['full_name_constructed']} (CB: {provider_info['cbcode']})\n"
                if api_info: details += f"Info API: {api_info['full_name']}"
            else: source = "API Validation"
        
        df.at[index, 'Bot_Accion'] = action
        df.at[index, 'Sugerencias_Bot'] = suggestion
        df.at[index, 'Bot_Detalles'] = details.strip()
        df.at[index, 'Source'] = source

    type_order = ['Surgeon', 'Provider', 'RCM', 'Coder']
    if 'Type' in df.columns:
        df['Type'] = pd.Categorical(df['Type'], categories=type_order, ordered=True)
        df_sorted = df.sort_values(by=['Type', 'Last - Title'], ascending=True, na_position='first')
        return df_sorted
    return df

def to_excel(df_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in df_dict.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    processed_data = output.getvalue()
    return processed_data

# ==============================================================================
# SECCIÓN 3: INTERFAZ Y EJECUCIÓN
# ==============================================================================
st.title("🤖 Asistente de Reporte CB Failed")
st.markdown("Herramienta para automatizar el análisis y la corrección del reporte diario.")

st.sidebar.header("1. Cargar Archivos")
uploaded_report = st.sidebar.file_uploader("A. Reporte CB FAILED (.xlsx)", type=['xlsx'])
uploaded_dictionaries = st.sidebar.file_uploader("B. Diccionarios (.txt)", type=['txt'], accept_multiple_files=True)
uploaded_corrections = st.sidebar.file_uploader("C. Correcciones de USAP (.xlsx)", type=['xlsx'], accept_multiple_files=True)

st.sidebar.header("2. Iniciar Proceso")
process_button = st.sidebar.button("✨ Procesar Reporte")

if process_button:
    if not uploaded_report or not uploaded_dictionaries:
        st.error("Por favor, carga el reporte principal y los diccionarios.")
    else:
        with st.spinner("Procesando... Esto puede tomar un minuto."):
            dictionaries_data = load_dictionaries_by_filename(uploaded_dictionaries)
            corrections_data = parse_usap_corrections(uploaded_corrections)
            
            st.info("Aprendiendo CB Codes de correcciones simples...")
            learned_cb_codes = {}
            try:
                temp_df_all_sheets = pd.concat(pd.read_excel(uploaded_report, sheet_name=None, dtype=str).values(), ignore_index=True).fillna('')
                for sin, corr in corrections_data.items():
                    if corr.get('type') == 'simple_correction' and corr.get('new_cb'):
                        original_row = temp_df_all_sheets[temp_df_all_sheets['SIN'] == sin]
                        if not original_row.empty:
                            npi = str(original_row.iloc[0].get('NPI', '')).replace('.0', '').strip()
                            if npi and npi != 'nan':
                                learned_cb_codes[npi] = corr['new_cb']
                st.info(f"Se aprendieron {len(learned_cb_codes)} nuevos CB Codes para aplicar globalmente.")
            except Exception as e: st.warning(f"No se pudo leer el reporte para aprendizaje: {e}")

            xls_input = pd.ExcelFile(uploaded_report)
            processed_sheets = {}
            for sheet_name in xls_input.sheet_names:
                df_sheet = pd.read_excel(xls_input, sheet_name=sheet_name, dtype=str).fillna('')
                if not df_sheet.empty and len(df_sheet.index) >= 1:
                    df_processed = process_dataframe(df_sheet, dictionaries_data, corrections_data, learned_cb_codes)
                    processed_sheets[sheet_name] = df_processed

            st.session_state['processed_sheets'] = processed_sheets
            st.session_state['report_name'] = uploaded_report.name
        st.success("¡Proceso completado!")

if 'processed_sheets' in st.session_state:
    st.header("3. Revisar y Descargar Resultados")
    processed_sheets = st.session_state['processed_sheets']
    
    all_actions = sorted(pd.concat(processed_sheets.values())['Bot_Accion'].unique().tolist())
    selected_actions = st.multiselect("Filtrar por Acción del Bot:", all_actions, default=all_actions)
    
    tabs = st.tabs(processed_sheets.keys())
    for i, sheet_name in enumerate(processed_sheets.keys()):
        with tabs[i]:
            st.markdown(f"**Resultados para: {sheet_name}**")
            df_display = processed_sheets[sheet_name]
            if selected_actions:
                df_display = df_display[df_display['Bot_Accion'].isin(selected_actions)]
            st.dataframe(df_display)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"PROCESADO_{timestamp}_{st.session_state['report_name']}"
    excel_data = to_excel(processed_sheets)
    
    st.download_button(
        label="📥 Descargar Reporte Procesado (.xlsx)",
        data=excel_data,
        file_name=output_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
