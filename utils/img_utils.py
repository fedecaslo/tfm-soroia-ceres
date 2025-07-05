import streamlit as st
from utils.db_utils import ejecutar_sql
import ast
import uuid
import boto3
import os
import base64

def obtener_ruta_final(path, version_app, s3_client=None):
    """
    Devuelve la ruta real del archivo de imagen con prefijo ./data/ o descarga desde S3 si es necesario.

    Args:
        path (str or list): Ruta o lista de rutas de la imagen.
        version_app (str): 'local' para entorno local, 'aws' para entorno en la nube.
        s3_client (boto3.client, optional): Cliente S3 para descargar archivos si es necesario.

    Returns:
        str or None: Ruta local del archivo de imagen, o None si falla la descarga.
    """
    if version_app=='local':
        try:
            # Convierte '["imagenes/00445/00445_1.jpg"]' a ['imagenes/00445/00445_1.jpg']
            parsed = ast.literal_eval(path) if isinstance(path, str) else path
            return './data/' + parsed[0] if isinstance(parsed, list) else './data/' + str(parsed)
        except Exception:
            return './data/' + str(path)
    elif version_app=='aws':
        try:
            parsed = ast.literal_eval(path) if isinstance(path, str) else path
            s3_key = parsed[0] if isinstance(parsed, list) else str(parsed)
        except Exception:
            s3_key = str(path)

        BUCKET_NAME = 'museosorolla'
        LOCAL_DIR = './data_s3_cache' 

        # Ruta local donde se guardará
        local_path = os.path.join(LOCAL_DIR, s3_key)
        # Crear el directorio si no existe
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        # Descargar solo si no existe ya
        if not os.path.exists(local_path):
            try:
                s3_client.download_file(BUCKET_NAME, s3_key, local_path)
            except Exception as e:
                print(f"Error al descargar {s3_key} desde S3: {e}")
                return None

        return local_path

def mostrar_imagenes_en_chat(imagenes, query_id, version_app='local', s3_client=None):
    """
    Muestra las imágenes en el chat de Streamlit.

    Args:
        imagenes (list): Lista de diccionarios con información de imágenes.
        query_id (str): Identificador único de la consulta.
        version_app (str, optional): 'local' o 'aws'. Por defecto 'local'.
        s3_client (boto3.client, optional): Cliente S3 para descarga si es necesario.
    """
    if not imagenes:
        return

    st.markdown("#### Imágenes encontradas")
    cols = st.columns(min(len(imagenes), 4))

    for i, imagen_dict in enumerate(imagenes):
        col = cols[i % 4]
        with col:
            imagen_path = obtener_ruta_final(imagen_dict["path"], version_app, s3_client=s3_client)
            st.image(imagen_path, width=150)

            inventario = imagen_dict["path"].split("/")[1]
            st.markdown(f"**Nº Inv.: {inventario}**")
            button_key = f"ver_{inventario}_{i}_{query_id}"

            if st.button("Ver", key=button_key):
                st.session_state.vista_detalle = {
                    "inventario": inventario,
                    "path": imagen_dict["path"]
                }


def mostrar_detalle_imagen(cursor, version_app):
    """
    Muestra la vista detallada de una imagen seleccionada desde el estado de Streamlit.

    Args:
        cursor: Cursor de la base de datos para ejecutar consultas.
        version_app (str): 'local' o 'aws' para determinar la fuente de la imagen.
    """
    # Verificamos si hay una imagen seleccionada
    if "vista_detalle" not in st.session_state or not st.session_state.vista_detalle:
        return

    detalle = st.session_state.vista_detalle

    col1, col2 = st.columns([2, 3])  # Dividimos la pantalla en dos columnas
    with col1:
        # Mostrar imagen ampliada
        imagen_path = obtener_ruta_final(detalle["path"], version_app)
        st.image(imagen_path, caption="Vista ampliada", use_container_width=True)

    with col2:
        # Buscar detalles de la obra en la base de datos usando el inventario
        consulta = f'SELECT * FROM fichas WHERE "Inventario" = \'{detalle["inventario"]}\' LIMIT 1;'
        resultados = ejecutar_sql(cursor, consulta)

        # Verificar si hay resultados
        if resultados:
            ficha = resultados[0]
            columnas = [desc[0] for desc in cursor.description]

            ficha_dict = dict(zip(columnas, ficha))

            # Orden de campos prioritarios
            orden_prioritario = [
                "Título", "Autor/a","Inventario", "Datación", "Año", "Colección", "Clasificación Genérica", 
                "Descripción", "Iconografia", "Clasificación Razonada", "Historia del objeto", "Lugar de Producción/Ceca","Objeto/Documento",
                "Técnica", "Materia/soporte", "Dimensiones", "Inscripciones/leyendas",
                "Firmas/marcas/etiquetas", "Forma de ingreso", "Museo", "Imagenes", "Bibliografía"
            ]

            st.markdown("### Ficha del objeto")
            mostrados = set()
            for campo in orden_prioritario:
                if campo in ficha_dict and ficha_dict[campo] not in [None, "", []]:
                    st.markdown(f"**{campo}**: {ficha_dict[campo]}")
                    mostrados.add(campo)
            # Mostrar el resto de campos
            for campo, valor in ficha_dict.items():
                if campo not in mostrados and valor not in [None, "", []]:
                    st.markdown(f"**{campo}**: {valor}")
        else:
            st.write("No se encontraron detalles para este inventario.")  # Si no hay resultados

    if st.button("Cerrar vista detallada"):
        del st.session_state.vista_detalle  # Limpiar la vista detallada
        st.rerun()

@st.cache_data
def get_base64_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

@st.cache_data
def load_banner():
    """
    Carga la imagen del banner y la convierte a base64.
    """
    banner_base64 = get_base64_image("static/nadadores.jpg")
    img_markdown = f"""
    <style>
    .banner img {{
        width: 100%;
        height: auto;
        display: block;
        margin-bottom: 20px;
    }}
    </style>
    <div class="banner">
        <img src="data:image/jpeg;base64,{banner_base64}" alt="Banner">
    </div>
    """
    return img_markdown
