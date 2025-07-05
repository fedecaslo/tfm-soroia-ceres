"""
app.py

SoroIA: Diseño e Implementación de un Sistema Conversacional basado en 
Modelos Grandes de Lenguaje para el Museo Sorolla
Proyecto de fin de máster, Máster en Ciencia de Datos
Computational Intelligence Group, Universidad Politécnica de Madrid. 

Autor: Federico Castejón Lozano
Fecha: julio 2025

"""

import streamlit as st
from utils.llm_utils import clasificar_intencion, llm_genera_sql, llm_sql_respuesta, obtener_contexto_chat, responder_interaccion
from utils.db_utils import ejecutar_sql
from utils.img_utils import mostrar_imagenes_en_chat, mostrar_detalle_imagen, load_banner
from utils.rag_utils import construir_retriever, generar_respuesta_rag
import psycopg2
import os
from dotenv import load_dotenv
from groq import Groq
import uuid
import boto3

# Configuración de la página de Streamlit
st.set_page_config(page_title="SoroIA", layout="wide")

# Cargar banner y guardar en cache
img_banner = load_banner()
st.markdown(img_banner, unsafe_allow_html=True)

# Cabecera de la aplicación
st.markdown(
    """
    <style>
    .footnote {
        font-size: 14px;
        color: gray;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    </style>
    <div class="footnote">
    © 2025 Federico Castejón. Proyecto de fin de máster. Computational Intelligence Group, Universidad Politécnica de Madrid. Fuentes de datos: Catálogo CER.es (ceres.mcu.es) y Ministerio de Cultura y Deporte (www.cultura.gob.es/msorolla/).     </div>
    """,
    unsafe_allow_html=True)

st.title("🎨 SoroIA: Asistente Museo Sorolla")

# Configuración de la aplicación
version_app = 'local' # 'local' o 'aws', para usar la base de datos e imágenes locales o de AWS
uso_pinecone = False # True o False, para usar Pinecone o FAISS
modo_desarrollo = False # True o False, para mostrar mensajes de depuración
llm_modelname = "llama-3.3-70b-versatile" # llama-3.3-70b-versatile o mistral-saba-24b
historial_activo = False # para activar el historial de chat

# Cargar variables de entorno
load_dotenv('./.env')

# Función para obtener conexión a la base de datos 
def get_db_connection(version_app):
    if version_app == 'local':
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
    elif version_app == 'aws':
        db_host = os.getenv("RDS_HOST")
        db_port = os.getenv("RDS_PORT")
        db_user = os.getenv("RDS_USER_IAM")
        db_name =  os.getenv("RDS_NAME")
        region = os.getenv("RDS_REGION")

        client = boto3.client('rds', region_name=region)
        token = client.generate_db_auth_token(DBHostname=db_host, Port=db_port, DBUsername=db_user, Region=region)

        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=token,
            sslmode='require'
        )

    else:
        raise ValueError("Versión de app no soportada")
    return conn

# Cliente de Groq en caché
@st.cache_resource(show_spinner=False)
def get_groq_client():
    return Groq(api_key=os.getenv("GROQ_API_KEY"))

# Cliente de S3 en caché
@st.cache_resource(show_spinner=False)
def get_s3_client():
	return boto3.client('s3')

# Inicializar clientes Groq y S3
groq_client = get_groq_client()
s3_client = get_s3_client()
print('New session SET UP Done!')
# Configuración de la página de Streamlit

# Inicializar estado del chat si no existe
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "¡Hola! Soy SoroIA, tu asistente virtual del Museo Sorolla. ¿En qué puedo ayudarte? Puedo hablarte de la vida de Joaquín Sorolla, del Museo Sorolla o sobre cualquier objeto del museo."}
    ]

# Inicializar el estado de la vista de detalle si no existe
if "vista_detalle" not in st.session_state:
    st.session_state.vista_detalle = None

# Inicializar el retriever si no se usa Pinecone y no existe en el estado
if not uso_pinecone:
    if "retriever" not in st.session_state:
        st.session_state.retriever = construir_retriever()

# Función principal para manejar la consulta del usuario
def manejar_consulta(consulta):
    st.session_state.query_id = str(uuid.uuid4())  # Nuevo id para cada consulta
    if not uso_pinecone:
        retriever = st.session_state.retriever # Recuperar el retriever del estado si no se usa Pinecone
    
    if historial_activo:
        contexto = obtener_contexto_chat(n=2) # Obtener contexto de las últimas 2 interacciones
    else:
        contexto = ""

    # Clasificar la intención de la consulta
    tipo = clasificar_intencion(groq_client, llm_modelname, consulta, contexto=contexto) 

    if modo_desarrollo:
        st.session_state.messages.append({"role": "system", "content": f"Clasificación: {tipo}"}) # para el modo desarrollador

    if modo_desarrollo:
            st.session_state.messages.append({"role": "system", "content": f"contexto: {contexto}"}) # para el modo desarrollador
    
    # Procesar según el tipo de consulta detectado
    if tipo == "SQL":
        # Usamos la función llm_genera_sql para generar la consulta SQL
        # y la función ejecutar_sql para ejecutarla en la base de datos.
        # Mostramos las imágenes asociadas a los resultados si existen
        # y generamos una respuesta con llm_sql_respuesta.
        # Si hay imágenes, las mostramos en el chat.
        # Si hay un error, lo capturamos y mostramos un mensaje de error.
        try:
            conn = get_db_connection(version_app)
            cursor = conn.cursor()
            sql_generado = llm_genera_sql(groq_client, llm_modelname, consulta, contexto=contexto)
            if modo_desarrollo:
                st.session_state.messages.append({"role": "system", "content": f"SQL generado:\n{sql_generado}"})
            resultados = ejecutar_sql(cursor, sql_generado)
            conn.close()
            columnas = [desc[0] for desc in cursor.description]

            imagenes = []
            if "imagenes" in columnas:
                idx_imagenes = columnas.index("imagenes")
                for fila in resultados:
                    if fila[idx_imagenes]:
                        imagenes.append({
                            "path": fila[idx_imagenes],
                            "titulo": fila[columnas.index("inventario")] if "inventario" in columnas else "Sin título"
                        })

            respuesta = llm_sql_respuesta(groq_client,llm_modelname, consulta, sql_generado, resultados)

            # Agregamos mensaje con imágenes si hay
            if imagenes:
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": respuesta,
                    "imagenes": imagenes,
                    "query_id": st.session_state.query_id # Campo adicional para las imágenes
                })
            else:
                st.session_state.messages.append({"role": "assistant", 
                                                  "content": respuesta,
                                                  "query_id": st.session_state.query_id
                                                  })

        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error al procesar la consulta SQL: {e}"
            })

    elif tipo == "RAG":
        # Usamos la función generar_respuesta_rag para generar una respuesta
        # basada en recuperación de documentos. Si se usa Pinecone, no pasamos el retriever.
        # Si no se usa Pinecone, pasamos el retriever construido anteriormente.
        # Si estamos en modo desarrollo, mostramos el contexto obtenido.
        if uso_pinecone:
            respuesta, contexto = generar_respuesta_rag(groq_client,llm_modelname, consulta,  contexto_anterior=contexto)
        else:
            respuesta, contexto = generar_respuesta_rag(groq_client, llm_modelname, consulta, retriever=retriever)
            #guardar_interaccion_csv(consulta, contexto, respuesta)

        if modo_desarrollo:
            st.session_state.messages.append({"role": "system", "content": f"Documentos obtenidos:\n{contexto}"})
        st.session_state.messages.append({"role": "assistant", "content": respuesta})
    
    elif tipo == "INTERACCION":
        # Usamos la función responder_interaccion para generar una respuesta amable.
        respuesta = responder_interaccion(groq_client,llm_modelname, consulta)
        st.session_state.messages.append({"role": "assistant", "content": respuesta})

    else:
        # Si la consulta no se clasifica como SQL, RAG o INTERACCION,
        # mostramos un mensaje indicando que no se reconoce la pregunta.
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Lo siento, la pregunta no parece estar relacionada con el Museo Sorolla o Joaquín Sorolla."
        })
    

# Entrada del usuario
if prompt := st.chat_input("Escribe tu mensaje aquí:"):
    # Limpiar vista anterior al hacer nueva consulta
    if "vista_detalle" in st.session_state:
        st.session_state.vista_detalle = None

    # Agregar mensaje del usuario al historial
    st.session_state.messages.append({"role": "user", "content": prompt})
    manejar_consulta(prompt)


# Mostrar historial del chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

        # Mostrar imágenes en el chat si existen
        if "imagenes" in message:
            mostrar_imagenes_en_chat(message["imagenes"], message.get("query_id", "default"), version_app, s3_client=s3_client)
        
        # Mostrar detalle de la imagen si se ha seleccionado
        if (
            "vista_detalle" in st.session_state
            and st.session_state.vista_detalle
            and any(
                st.session_state.vista_detalle["path"] == img["path"]
                for img in message.get("imagenes", [])
            )):
            conn = get_db_connection(version_app)
            cursor = conn.cursor()
            mostrar_detalle_imagen(cursor, version_app)
            conn.close()
